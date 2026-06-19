"""Commit a completed `ScanResult` to the database.

Two write paths:

- `persist_pending_scan` — called from POST /scans before the engine runs.
  Creates the `scans` row in `status=pending` with placeholder score values;
  this gives us a `scan_id` to return to the client before the work starts.
- `persist_completed_scan` — called from the queue worker after the engine
  returns. Updates the `scans` row with the real aggregate + sub-scores +
  score_breakdown, and bulk-inserts the `findings` rows.

CatalogItem creation/lookup: the scan engine submits a github_url; we
upsert a `catalog_items` row keyed on `(slug = "<org>--<repo>")` so subsequent
scans of the same repo update the same catalog entry.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.artifact_blob import ArtifactBlob
from app.models.catalog_item import CatalogItem
from app.models.scan import Finding, Scan, ScanEvent
from app.models.scan_run import ScanRun
from app.models.upload_file import UploadFile
from app.scan.discovery import (
    _is_repo_wide,  # pyright: ignore[reportPrivateUsage]
    build_install_spec,
)
from app.scan.engine import CapabilityResult, RepoScanResult, ScanResult
from app.scan.fetch import GithubRef, parse_github_url
from app.services.agent_compat import agent_compatibility_for
from app.services.repository_metadata import RepositoryMetadata, get_repository_metadata

_MANIFEST_MAX_BYTES = 64 * 1024  # cap the stored public manifest at 64 KiB
# Per-file cap on what we store in artifact_blobs (matches the engine's per-file
# fetch cap). Files above this are recorded as present-but-not-stored.
_SNAPSHOT_MAX_PER_FILE_BYTES = 5 * 1024 * 1024
# Flush the artifact_blobs INSERT in chunks so the whole repo's bytes are never
# copied into one statement's wire buffer at once (a transient ~repo-size memory
# spike on top of the in-memory index). Same transaction, same ON CONFLICT.
_SNAPSHOT_INSERT_CHUNK_BYTES = 4 * 1024 * 1024
_SNAPSHOT_INSERT_CHUNK_ROWS = 400


def _looks_binary(content: bytes) -> bool:
    """Null-byte heuristic — a NUL in the first 8 KiB ⇒ treat as binary.

    Cheap and good enough to separate text we line-diff from binaries we only
    record as present (path → null sentinel), without a charset-detection dep.
    """
    return b"\x00" in content[:8192]


def _decode_manifest_text(content: bytes) -> str:
    """Decode manifest bytes to text safe for a Postgres `text`/`varchar` column.

    BOM-aware: a UTF-16 / UTF-8-SIG manifest (Windows-authored READMEs are common
    in the wild) decodes correctly instead of degrading to a wall of replacement
    chars. Postgres text columns cannot store U+0000, so NUL chars are stripped
    unconditionally as the final guarantee — a UTF-16 file naively decoded as
    UTF-8 keeps its interleaved NULs (U+0000 is itself valid UTF-8, so
    `errors="replace"` does NOT remove them) and would otherwise crash the
    `manifest_source` write with `CharacterNotInRepertoireError`.
    """
    if content.startswith((b"\xff\xfe", b"\xfe\xff")):
        text = content.decode("utf-16", errors="replace")
    elif content.startswith(b"\xef\xbb\xbf"):
        text = content.decode("utf-8-sig", errors="replace")
    else:
        text = content.decode("utf-8", errors="replace")
    return text.replace("\x00", "")


async def _capture_snapshot(
    session: AsyncSession,
    files_index: list[tuple[str, bytes]],
) -> dict[str, str | None]:
    """Persist scanned text files (deduped, content-addressed) → file_hashes map.

    For each text file within the per-file cap: `sha = sha256(content)`, upsert
    into `artifact_blobs` with `on_conflict_do_nothing` on the sha PK (global
    content-addressed dedup), and record `{path: sha}`. Binaries / oversize
    files are known-but-not-stored: `{path: null}`. Returns the `{path: sha|null}`
    map for `scan.file_hashes`.

    Verbatim public-repo bytes at the scanned ref — reproduction of
    already-public data, not new disclosure (`.claude/rules/security.md`
    § Vendor-data isolation → stored public artifact snapshots). The scan trace
    stays no-raw-payload; this is a separate stored-snapshot feature.
    """
    file_map: dict[str, str | None] = {}
    # Dedup within this scan (by sha) so identical bytes never insert twice; the
    # ON CONFLICT then dedups globally. Rows are flushed in chunks — the whole
    # repo's bytes are never marshalled into one statement at once.
    seen_sha: set[str] = set()
    chunk: list[dict[str, object]] = []
    chunk_bytes = 0
    insert_stmt = pg_insert(ArtifactBlob).on_conflict_do_nothing(index_elements=["sha256"])

    async def _flush() -> None:
        nonlocal chunk, chunk_bytes
        if chunk:
            await session.execute(insert_stmt, chunk)
            chunk = []
            chunk_bytes = 0

    for path, content in files_index:
        if _looks_binary(content) or len(content) > _SNAPSHOT_MAX_PER_FILE_BYTES:
            file_map[path] = None
            continue
        sha = hashlib.sha256(content).hexdigest()
        file_map[path] = sha
        if sha in seen_sha:
            continue
        seen_sha.add(sha)
        chunk.append(
            {"sha256": sha, "content": content, "byte_size": len(content), "is_binary": False}
        )
        chunk_bytes += len(content)
        if len(chunk) >= _SNAPSHOT_INSERT_CHUNK_ROWS or chunk_bytes >= _SNAPSHOT_INSERT_CHUNK_BYTES:
            await _flush()

    await _flush()
    return file_map


def _snapshot_identity(file_map: dict[str, str | None]) -> str:
    """Stable content hash of the whole snapshot (sorted {path: sha} map).

    A single identity for the scanned tree — reuses the dead
    `catalog_items.content_hash_sha256` column and enables future drift
    detection (a changed identity ⇒ the repo's tracked files moved).
    """
    canonical = json.dumps(file_map, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _upload_file_hashes(files_index: list[tuple[str, bytes]]) -> dict[str, str | None]:
    """`{path: sha256|null}` for a capability subset WITHOUT storing bytes.

    The unlisted-upload counterpart map to `_capture_snapshot`'s return — the
    bytes themselves are stored once per run by `_store_upload_files`. Same
    binary/oversize sentinel rule (null) so the resolver + diff stay uniform.
    """
    file_map: dict[str, str | None] = {}
    for path, content in files_index:
        if _looks_binary(content) or len(content) > _SNAPSHOT_MAX_PER_FILE_BYTES:
            file_map[path] = None
        else:
            file_map[path] = hashlib.sha256(content).hexdigest()
    return file_map


async def _store_upload_files(
    session: AsyncSession, run_id: UUID, files_index: list[tuple[str, bytes]]
) -> None:
    """Persist a run's uploaded text bytes into `upload_files` ONCE (no dedup).

    Per-run isolation (vs the global `artifact_blobs`) avoids dedup-induced
    privacy coupling — two users' identical unlisted bytes never share a row.
    De-dups within the run by path so shared repo-wide files (LICENSE, README)
    aren't inserted once per capability. Binaries/oversize are stored as a
    present-but-not-stored sentinel (`content = NULL`).
    """
    rows: list[dict[str, object]] = []
    seen: set[str] = set()
    for path, content in files_index:
        if path in seen:
            continue
        seen.add(path)
        is_bin = _looks_binary(content) or len(content) > _SNAPSHOT_MAX_PER_FILE_BYTES
        rows.append(
            {
                "scan_run_id": run_id,
                "path": path,
                "content": None if is_bin else content,
                "byte_size": len(content),
                "is_binary": is_bin,
            }
        )
    if rows:
        await session.execute(pg_insert(UploadFile), rows)


def _pick_manifest(files_index: list[tuple[str, bytes]], kind: str) -> tuple[str, str] | None:
    """Pick the primary public manifest to surface on the item Source tab.

    Skills lead with SKILL.md; everything else falls back to README.md, then any
    manifest-ish file. Returns (relative_path, decoded_source) size-capped, or
    None. Public repo content only — never a scan-trace payload.
    """
    # Preference order by basename (lowercased).
    preferred = ["skill.md", "readme.md", "manifest.json", "package.json"]
    if kind != "skill":
        preferred = ["readme.md", "skill.md", "manifest.json", "package.json"]

    by_base: dict[str, tuple[str, bytes]] = {}
    for path, content in files_index:
        base = path.rsplit("/", 1)[-1].lower()
        # Keep the shallowest path for a given basename (root README over nested).
        if base not in by_base or path.count("/") < by_base[base][0].count("/"):
            by_base[base] = (path, content)

    for base in preferred:
        hit = by_base.get(base)
        if hit is not None:
            path, content = hit
            text = _decode_manifest_text(content[:_MANIFEST_MAX_BYTES])
            return path, text

    # Fallback: a loose single-file capability (install.sh / server.json /
    # .cursorrules) has no preferred manifest — surface its own bytes so the Source
    # tab isn't empty. Only when exactly one non-repo-wide text file is in scope.
    non_wide = [(p, c) for p, c in files_index if not _is_repo_wide(p) and not _looks_binary(c)]
    if len(non_wide) == 1:
        path, content = non_wide[0]
        text = _decode_manifest_text(content[:_MANIFEST_MAX_BYTES])
        return path, text
    return None


def compute_idempotency_key(
    github_url: str, ref_sha: str, rubric_version: str, *, nonce: str | None = None
) -> str:
    """SHA-256 idempotency key per scan-report.schema.json contract.

    `nonce` is OMITTED for public scans, so the public key stays byte-identical to
    the earlier public-only form (existing cached runs still hit). An unlisted
    submission passes a per-submission nonce so two identical private submissions
    never collapse onto one run/token.
    """
    raw = f"{github_url}|{ref_sha}|{rubric_version}"
    if nonce is not None:
        raw = f"{raw}|{nonce}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def slug_for(ref: GithubRef) -> str:
    """`<org>--<repo>` URL-safe slug."""
    return f"{ref.org.lower()}--{ref.repo.lower()}"


def display_name_for(ref: GithubRef) -> str:
    """Human-readable display name for a fresh CatalogItem."""
    return ref.repo.replace("-", " ").replace("_", " ").title()


def _slugify(text: str) -> str:
    """Lowercase, collapse non-alnum runs to single dashes, strip edges."""
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def capability_slug(ref: GithubRef, kind: str, name: str) -> str:
    """Per-capability slug `<org>--<repo>--<kind>-<name>[-<hash6>]`.

    The `<kind>-<name>` tail distinguishes the several capabilities a single repo
    may host. `mcp_server` → `mcp-server` (slug grammar disallows underscores);
    name collisions are already hash-disambiguated upstream in
    `app.scan.discovery`. Capped at the 255-char slug ceiling.
    """
    base = slug_for(ref)
    kind_seg = kind.replace("_", "-")
    name_seg = _slugify(name) or _slugify(ref.repo) or "item"
    return f"{base}--{kind_seg}-{name_seg}"[:255]


def upload_capability_slug(content_hash: str, kind: str, name: str | None) -> str:
    """Public-upload per-capability slug `upload--<arthash8>--<kind>-<name>`.

    `arthash8` = `scan_runs.content_hash_sha256[:8]`. Satisfies the widened slug
    grammar `^[a-z0-9][a-z0-9-]*(--[a-z0-9][a-z0-9-]*)+$` (multiple `--` segments).
    """
    kind_seg = kind.replace("_", "-")
    name_seg = _slugify(name or "") or "artifact"
    return f"upload--{content_hash[:8]}--{kind_seg}-{name_seg}"[:255]


def unlisted_capability_slug(run_id: UUID, kind: str, name: str | None) -> str:
    """Per-run unlisted SHADOW slug `unlisted--<run8>--<kind>-<name>` (any source).

    `run8` = `str(run_id)[:8]`. Shadow slugs never reach the public catalog —
    `/items/<unlisted-slug>` 404s (visibility filter); they exist only so the
    report `JOIN catalog_items` + diff/download paths keep working per-run.
    """
    kind_seg = kind.replace("_", "-")
    name_seg = _slugify(name or "") or "artifact"
    return f"unlisted--{str(run_id)[:8]}--{kind_seg}-{name_seg}"[:255]


async def ensure_capability_item(
    session: AsyncSession, ref: GithubRef, github_url: str, cap: CapabilityResult
) -> CatalogItem:
    """Upsert the catalog_items row for one discovered capability, keyed on its
    per-capability slug. `kind` comes from the capability (no longer a hardcoded
    `"skill"`); rescans resolve to the same slug and update in place.
    """
    slug = capability_slug(ref, cap.kind, cap.name)
    stmt = select(CatalogItem).where(CatalogItem.slug == slug)
    existing = (await session.execute(stmt)).scalar_one_or_none()
    if existing is not None:
        return existing

    item = CatalogItem(
        kind=cap.kind,
        slug=slug,
        display_name=cap.name or display_name_for(ref),
        github_url=github_url,
        github_org=ref.org,
        github_repo=ref.repo,
        default_branch="main",
        popularity_tier="indexed",
        popularity_score=0,
        agent_compatibility=agent_compatibility_for(cap.kind),
        sources=[],
    )
    session.add(item)
    await session.flush()
    return item


async def _slug_exists(session: AsyncSession, slug: str) -> bool:
    return (
        await session.execute(select(CatalogItem.id).where(CatalogItem.slug == slug))
    ).first() is not None


def _disambiguate(slug: str, salt: str) -> str:
    """Append a deterministic 6-hex suffix on a within-run slug collision."""
    suffix = hashlib.sha256(f"{slug}|{salt}".encode()).hexdigest()[:6]
    return f"{slug}-{suffix}"[:255]


def _upload_display_name(run: ScanRun, cap: CapabilityResult) -> str:
    return cap.name or run.original_filename or "Uploaded artifact"


def _upload_source(run: ScanRun) -> dict[str, object]:
    """The `sources[]` entry for a public-upload catalog row.

    `registryId='upload'`; `registryUrl` is the run-report URL so the upload item
    validates against the (non-empty) catalog-item `sources` contract.
    """
    base = get_settings().public_base_url.rstrip("/")
    ts = (run.scanned_at or datetime.now(UTC)).isoformat()
    return {
        "registryId": "upload",
        "registryUrl": f"{base}/scans/{run.id}",
        "firstIndexedAt": ts,
        "lastSeenAt": ts,
    }


async def ensure_upload_capability_item(
    session: AsyncSession, run: ScanRun, cap: CapabilityResult
) -> CatalogItem:
    """Upsert the CANONICAL public-upload catalog row for one capability.

    Slug `upload--<arthash8>--<kind>-<name>`; `visibility='public'`,
    `source_kind='upload'`, `owner_run_id=NULL`, no GitHub provenance, and a
    `sources=[{registryId:'upload', …}]` attribution. Idempotent on the slug.
    """
    content_hash = run.content_hash_sha256 or "00000000"
    slug = upload_capability_slug(content_hash, cap.kind, cap.name)
    existing = (
        await session.execute(select(CatalogItem).where(CatalogItem.slug == slug))
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    item = CatalogItem(
        kind=cap.kind,
        slug=slug,
        display_name=_upload_display_name(run, cap),
        github_url=None,
        github_org=None,
        github_repo=None,
        default_branch=None,
        popularity_tier="on_demand",
        popularity_score=0,
        agent_compatibility=agent_compatibility_for(cap.kind),
        visibility="public",
        source_kind="upload",
        owner_run_id=None,
        sources=[_upload_source(run)],
    )
    session.add(item)
    await session.flush()
    return item


async def create_unlisted_shadow_item(
    session: AsyncSession, run: ScanRun, cap: CapabilityResult, *, ref: GithubRef | None
) -> CatalogItem:
    """Create a FRESH per-run unlisted SHADOW catalog row.

    Never reuses/mutates a canonical row (that would collapse a public+unlisted
    scan of the same repo onto one slug, or violate the slug UNIQUE). Slug
    `unlisted--<run8>--<kind>-<name>`; `visibility='unlisted'`,
    `owner_run_id=run.id` (FK CASCADE). `github_url` stays NULL even for a github
    source — the canonical public row owns the UNIQUE(github_url); the shadow row
    keeps org/repo for display/rescan only.
    """
    slug = unlisted_capability_slug(run.id, cap.kind, cap.name)
    if await _slug_exists(session, slug):
        slug = _disambiguate(slug, cap.component_path or "")

    is_github = run.source_kind == "github"
    item = CatalogItem(
        kind=cap.kind,
        slug=slug,
        display_name=cap.name
        or (display_name_for(ref) if ref is not None else None)
        or run.original_filename
        or "Unlisted artifact",
        github_url=None,
        github_org=ref.org if ref is not None else None,
        github_repo=ref.repo if ref is not None else None,
        default_branch="main" if is_github else None,
        popularity_tier="on_demand",
        popularity_score=0,
        agent_compatibility=agent_compatibility_for(cap.kind),
        visibility="unlisted",
        source_kind=run.source_kind,
        owner_run_id=run.id,
        sources=[],
    )
    session.add(item)
    await session.flush()
    return item


def _placeholder_scan(
    catalog_item_id: UUID,
    idempotency_key: str,
    github_url: str,
    rubric_version: str,
    engine_version: str,
    source: str,
) -> Scan:
    """Initial scan row — the queue worker updates score columns on completion."""
    return Scan(
        catalog_item_id=catalog_item_id,
        idempotency_key=idempotency_key,
        github_url=github_url,
        ref_sha="0" * 40,
        aggregate_score=0,
        tier="unscoped",
        sub_scores={
            "security": 0,
            "supply_chain": 0,
            "maintenance": 0,
            "transparency": 0,
            "community": 0,
        },
        score_breakdown={"status": "pending"},
        rubric_version=rubric_version,
        engine_version=engine_version,
        latency_ms=0,
        source=source,
    )


async def persist_pending_scan(
    session: AsyncSession,
    *,
    catalog_item_id: UUID,
    idempotency_key: str,
    github_url: str,
    rubric_version: str,
    engine_version: str,
    source: str,
) -> Scan:
    """Insert the initial scans row + return it. Idempotent on idempotency_key."""
    existing_stmt = select(Scan).where(Scan.idempotency_key == idempotency_key)
    cached = (await session.execute(existing_stmt)).scalar_one_or_none()
    if cached is not None:
        return cached

    scan = _placeholder_scan(
        catalog_item_id=catalog_item_id,
        idempotency_key=idempotency_key,
        github_url=github_url,
        rubric_version=rubric_version,
        engine_version=engine_version,
        source=source,
    )
    session.add(scan)
    await session.flush()
    return scan


def _apply_repository_metadata(item: CatalogItem, meta: RepositoryMetadata) -> None:
    """Mirror public GitHub metadata onto a catalog item (best-effort)."""
    if meta.stars is not None:
        item.github_stars = meta.stars
    if meta.forks is not None:
        item.github_forks = meta.forks
    if meta.license_spdx is not None:
        item.license_spdx = meta.license_spdx
    if meta.latest_version is not None:
        item.latest_version = meta.latest_version


async def _apply_scan_result(
    session: AsyncSession,
    scan: Scan,
    result: ScanResult,
    *,
    item: CatalogItem | None,
    meta: RepositoryMetadata | None,
    upload_run_id: UUID | None = None,
    install_spec: dict[str, object] | None = None,
) -> None:
    """Fill a (flushed) scan row from an engine result: score, findings, manifest,
    snapshot. Shared by the single-scan and per-capability-run write paths.

    `scan` must already have an `id` (flush before calling). Existing findings
    for the scan are cleared first so a rescan-in-place never double-inserts.

    Byte store fork: when `upload_run_id` is set (unlisted upload), the bytes were
    stored once in `upload_files` for the run — this capability only records its
    `{path: sha|null}` map (no `artifact_blobs` write). Otherwise bytes capture to
    the deduped `artifact_blobs` via `_capture_snapshot`.
    """
    scan.aggregate_score = result.aggregate_score
    scan.tier = result.tier
    scan.sub_scores = dict(result.sub_scores)
    scan.score_breakdown = dict(result.score_breakdown)
    scan.ref_sha = result.ref_sha
    scan.latency_ms = result.latency_ms

    await session.execute(delete(Finding).where(Finding.scan_id == scan.id))
    if result.findings:
        await session.execute(
            pg_insert(Finding),
            [
                {
                    "scan_id": scan.id,
                    "rule_id": f.rule_id,
                    "severity": f.severity,
                    "sub_score": f.sub_score,
                    "penalty": f.penalty,
                    "status_at_scan": f.status_at_scan,
                    "file_path": f.file_path,
                    "line_start": f.line_start,
                    "line_end": f.line_end,
                    "matched_content_sha256": f.matched_content_sha256,
                    "remediation_link": f.remediation_link,
                    "rubric_version": f.rubric_version,
                }
                for f in result.findings
            ],
        )

    if item is not None:
        if meta is not None:
            _apply_repository_metadata(item, meta)
        # Capture this capability's primary public manifest (its own SKILL.md /
        # README within the subtree) for the item Source tab.
        manifest = _pick_manifest(result.files_index, item.kind)
        if manifest is not None:
            scan.manifest_path, scan.manifest_source = manifest

        # Per-capability install descriptor for the `saferskills` CLI. The run
        # fan-out passes the discovery-derived spec; the legacy single-scan path
        # re-derives from the capability's own (already-public) bytes so a
        # vendor rescan keeps it populated.
        scan.install_spec = (
            install_spec
            if install_spec is not None
            else build_install_spec(item.kind, result.files_index, scan.component_path or "")
        )

        # Persist the per-capability text-file snapshot for diffs + zip. Unlisted
        # uploads resolve from the per-run upload_files store (bytes already
        # written once for the run); everything else dedups into artifact_blobs.
        if upload_run_id is not None:
            file_map = _upload_file_hashes(result.files_index)
        else:
            file_map = await _capture_snapshot(session, result.files_index)
        scan.file_hashes = file_map
        item.content_hash_sha256 = _snapshot_identity(file_map)


async def persist_completed_scan(
    session: AsyncSession,
    scan: Scan,
    result: ScanResult,
) -> Scan:
    """Update a single scan with score breakdown + findings + snapshot.

    Back-compat path (vendor-triggered single-capability rescans + the legacy
    `scan_run` worker). The repo-scan fan-out uses `persist_completed_scan_run`.
    """
    item = await session.get(CatalogItem, scan.catalog_item_id)
    meta: RepositoryMetadata | None = None
    if item is not None and item.github_org and item.github_repo:
        # Refresh public GitHub metadata (off the request path, cached ~1h,
        # best-effort — never fail a scan over metadata). Skipped for uploads
        # (no GitHub provenance).
        meta = await get_repository_metadata(item.github_org, item.github_repo)
    await _apply_scan_result(session, scan, result, item=item, meta=meta)
    await session.flush()
    return scan


async def persist_pending_scan_run(
    session: AsyncSession,
    *,
    idempotency_key: str,
    github_url: str | None,
    rubric_version: str,
    engine_version: str,
    source: str,
    visibility: str = "public",
    source_kind: str = "github",
    share_token: str | None = None,
    expires_at: datetime | None = None,
    original_filename: str | None = None,
    content_hash_sha256: str | None = None,
) -> ScanRun:
    """Insert the initial `scan_runs` row + return it. Idempotent on the run's
    idempotency_key — this is the id the submit response + SSE channel key on.

    The upload/visibility kwargs (`visibility`/`source_kind`/`share_token`/
    `expires_at`/`original_filename`/`content_hash_sha256`) default to the
    GitHub-public shape, so existing callers are unchanged.
    """
    cached = (
        await session.execute(select(ScanRun).where(ScanRun.idempotency_key == idempotency_key))
    ).scalar_one_or_none()
    if cached is not None:
        return cached

    run = ScanRun(
        idempotency_key=idempotency_key,
        github_url=github_url,
        ref_sha=None,
        repo_aggregate_score=0,
        repo_tier="unscoped",
        kind_tally={},
        capability_count=0,
        rubric_version=rubric_version,
        engine_version=engine_version,
        source=source,
        latency_ms=0,
        file_count=0,
        status="pending",
        visibility=visibility,
        source_kind=source_kind,
        share_token=share_token,
        expires_at=expires_at,
        original_filename=original_filename,
        content_hash_sha256=content_hash_sha256,
    )
    session.add(run)
    await session.flush()
    return run


def _capability_scan_key(run: ScanRun, cap: CapabilityResult) -> str:
    """Stable per-capability idempotency key (`scans.idempotency_key` is UNIQUE).

    Source-aware identity so cross-run collisions can't happen (uploads have
    `github_url = NULL`):
    - **github public** — keyed on the repo URL, so a rescan updates the same
      scan row in place (byte-identical to the earlier github-only key).
    - **upload public** — keyed on the artifact content hash (distinct artifacts →
      distinct rows; identical bytes cache at the run level, never re-persist).
    - **unlisted (any)** — keyed on the run id, so every unlisted run is fully
      isolated (two identical private submissions never share a scan row).
    """
    if run.visibility == "unlisted":
        identity = f"run:{run.id}"
    elif run.source_kind == "upload":
        identity = f"upload:{run.content_hash_sha256}"
    else:
        identity = run.github_url or ""
    return compute_idempotency_key(
        f"{identity}#{cap.component_path}#{cap.kind}",
        ref_sha="0" * 40,
        rubric_version=run.rubric_version,
    )


async def persist_completed_scan_run(
    session: AsyncSession,
    run: ScanRun,
    repo_result: RepoScanResult,
    *,
    full_files_index: list[tuple[str, bytes]] | None = None,
) -> ScanRun:
    """Fan out a completed repo/upload scan into N catalog items + N scans, then
    write the repo rollup onto the run.

    The per-capability fan-out is shared; only **(a) the catalog-item builder**
    and **(b) the byte store** fork on source x visibility:

    | visibility | catalog item | byte store |
    |---|---|---|
    | public github | `ensure_capability_item` (canonical) | `artifact_blobs` |
    | public upload | `ensure_upload_capability_item` (canonical) | `artifact_blobs` |
    | unlisted (any) | `create_unlisted_shadow_item` (fresh shadow) | github → `artifact_blobs`; upload → `upload_files` |

    `full_files_index` is the original upload index (required for unlisted uploads
    to store bytes once per run); it is None for GitHub scans.
    """
    is_upload = run.source_kind == "upload"
    is_unlisted = run.visibility == "unlisted"
    use_upload_files = is_upload and is_unlisted

    ref: GithubRef | None = None
    meta: RepositoryMetadata | None = None
    if not is_upload and run.github_url is not None:
        ref = parse_github_url(run.github_url)
        meta = await get_repository_metadata(ref.org, ref.repo)

    # Store unlisted-upload bytes ONCE for the run (per-run, no dedup).
    if use_upload_files and full_files_index is not None:
        await _store_upload_files(session, run.id, full_files_index)

    for cap in repo_result.capabilities:
        if is_unlisted:
            item = await create_unlisted_shadow_item(session, run, cap, ref=ref)
        elif is_upload:
            item = await ensure_upload_capability_item(session, run, cap)
        else:
            assert ref is not None  # github-public always parses a ref
            item = await ensure_capability_item(session, ref, run.github_url or "", cap)

        cap_key = _capability_scan_key(run, cap)
        scan = (
            await session.execute(select(Scan).where(Scan.idempotency_key == cap_key))
        ).scalar_one_or_none()
        if scan is None:
            scan = Scan(
                catalog_item_id=item.id,
                scan_run_id=run.id,
                component_path=cap.component_path or None,
                idempotency_key=cap_key,
                # Uploads set both NULL (no synthetic sentinel). GitHub keeps real.
                github_url=None if is_upload else run.github_url,
                ref_sha=None if is_upload else cap.result.ref_sha,
                aggregate_score=0,
                tier="unscoped",
                sub_scores={},
                score_breakdown={},
                rubric_version=run.rubric_version,
                engine_version=run.engine_version,
                latency_ms=0,
                source=run.source,
            )
            session.add(scan)
            await session.flush()  # assign scan.id before findings insert
        else:
            scan.scan_run_id = run.id
            scan.component_path = cap.component_path or None
        await _apply_scan_result(
            session,
            scan,
            cap.result,
            item=item,
            meta=meta,
            upload_run_id=run.id if use_upload_files else None,
            install_spec=cap.install_spec,
        )
        if is_upload:
            # `_apply_scan_result` copies the engine's sentinel ref_sha; uploads
            # have no git ref, so keep both NULL (no synthetic value).
            scan.github_url = None
            scan.ref_sha = None

    run.repo_aggregate_score = repo_result.repo_aggregate_score
    run.repo_tier = repo_result.repo_tier
    run.kind_tally = dict(repo_result.kind_tally)
    run.capability_count = repo_result.capability_count
    run.ref_sha = repo_result.ref_sha
    run.file_count = repo_result.file_count
    run.latency_ms = repo_result.latency_ms
    run.status = "completed"
    await session.flush()
    return run


def _promoted_item(item: CatalogItem, *, merged: bool) -> dict[str, object]:
    return {
        "slug": item.slug,
        "kind": item.kind,
        "display_name": item.display_name,
        "merged": merged,
    }


async def run_catalog_item_slugs(session: AsyncSession, run_id: UUID) -> list[str]:
    """Public: the distinct catalog-item slugs linked to a run via its scans.

    Used by the post-commit IndexNow hook (`app/queue/scan_runner.py`) to re-derive
    the per-capability slugs the persist fan-out builds internally — without
    reaching into the private `_run_catalog_items`.
    """
    return [item.slug for item in await _run_catalog_items(session, run_id)]


async def _run_catalog_items(session: AsyncSession, run_id: UUID) -> list[CatalogItem]:
    """Distinct catalog items linked to a run via its scans (any visibility)."""
    rows = (
        (
            await session.execute(
                select(CatalogItem)
                .join(Scan, Scan.catalog_item_id == CatalogItem.id)
                .where(Scan.scan_run_id == run_id)
                .distinct()
            )
        )
        .scalars()
        .all()
    )
    return list(rows)


async def promote_run_to_public(
    session: AsyncSession, run: ScanRun
) -> tuple[bool, list[dict[str, object]]]:
    """Promote an unlisted run → public, one-way. Returns
    `(promoted, items)` where `items` is one `{slug,kind,display_name,merged}`
    per capability. Idempotent: an already-public run is a `(False, items)` no-op.

    For each shadow catalog row owned by the run: compute its canonical public
    slug; if a canonical row already exists, MERGE (repoint the run's scans to it,
    delete the shadow → `merged=True`); else re-slug in place + clear
    `owner_run_id` (→ canonical, `merged=False`). Upload bytes migrate
    `upload_files → artifact_blobs` (the shas already match the scans' file_hashes,
    so nothing else changes); `expires_at` is cleared. `share_token` is kept so the
    old link still resolves (it then redirects to the run report).
    """
    if run.visibility == "public":
        items = await _run_catalog_items(session, run.id)
        return False, [_promoted_item(it, merged=False) for it in items]

    is_upload = run.source_kind == "upload"
    ref: GithubRef | None = None
    if not is_upload and run.github_url is not None:
        ref = parse_github_url(run.github_url)

    # Migrate upload bytes into the public dedup store, then drop the per-run rows.
    if is_upload:
        rows = (
            (await session.execute(select(UploadFile).where(UploadFile.scan_run_id == run.id)))
            .scalars()
            .all()
        )
        files_index = [(r.path, bytes(r.content)) for r in rows if r.content is not None]
        if files_index:
            await _capture_snapshot(session, files_index)
        await session.execute(delete(UploadFile).where(UploadFile.scan_run_id == run.id))

    shadow_items = (
        (await session.execute(select(CatalogItem).where(CatalogItem.owner_run_id == run.id)))
        .scalars()
        .all()
    )

    promoted: list[dict[str, object]] = []
    for item in shadow_items:
        if is_upload:
            canonical_slug = upload_capability_slug(
                run.content_hash_sha256 or "00000000", item.kind, item.display_name
            )
        elif ref is not None:
            canonical_slug = capability_slug(ref, item.kind, item.display_name)
        else:
            canonical_slug = item.slug  # no ref — keep slug, just flip visibility

        existing = (
            await session.execute(
                select(CatalogItem).where(
                    CatalogItem.slug == canonical_slug, CatalogItem.owner_run_id.is_(None)
                )
            )
        ).scalar_one_or_none()

        if existing is not None and existing.id != item.id:
            await session.execute(
                update(Scan)
                .where(Scan.catalog_item_id == item.id)
                .values(catalog_item_id=existing.id)
            )
            existing.visibility = "public"
            await session.delete(item)
            promoted.append(_promoted_item(existing, merged=True))
        else:
            item.slug = canonical_slug
            item.visibility = "public"
            item.owner_run_id = None
            if is_upload and not item.sources:
                item.github_url = None
                item.sources = [_upload_source(run)]
            elif ref is not None:
                item.github_url = run.github_url
                item.github_org = ref.org
                item.github_repo = ref.repo
            promoted.append(_promoted_item(item, merged=False))

    run.visibility = "public"
    run.expires_at = None
    await session.flush()
    return True, promoted


async def select_existing_run_by_idempotency(
    session: AsyncSession, idempotency_key: str
) -> ScanRun | None:
    stmt = select(ScanRun).where(ScanRun.idempotency_key == idempotency_key)
    return (await session.execute(stmt)).scalar_one_or_none()


async def select_existing_by_idempotency(
    session: AsyncSession, idempotency_key: str
) -> Scan | None:
    stmt = select(Scan).where(Scan.idempotency_key == idempotency_key)
    return (await session.execute(stmt)).scalar_one_or_none()


async def delete_run_cascade(
    session: AsyncSession, run_id: UUID, *, allow_public: bool = False
) -> None:
    """Explicit ordered delete of a run and everything it owns.

    The `scans -> scan_runs` FK is `ON DELETE SET NULL` (0007), so scans MUST be
    deleted BEFORE the run — never rely on the FK (it would orphan scans and leave
    their findings). Order:

        findings (by scan_id ∈ run's scans)
          → scan_events (by scan_run_id)
          → scans (by scan_run_id)
          → shadow catalog_items (owner_run_id only — NEVER a canonical row)
          → upload_files (by scan_run_id)
          → scan_runs (the run)

    Never touches `artifact_blobs` (public/dedup; orphans reaped by a separate
    sweep). Token-delete + the expiry sweep call with `allow_public=False` (refuse
    a public run); only the operator runbook passes `allow_public=True`.
    """
    run = await session.get(ScanRun, run_id)
    if run is None:
        return
    if run.visibility == "public" and not allow_public:
        raise ValueError("refusing to delete a public run via delete_run_cascade")

    scan_ids = list(
        (await session.execute(select(Scan.id).where(Scan.scan_run_id == run_id))).scalars().all()
    )
    if scan_ids:
        await session.execute(delete(Finding).where(Finding.scan_id.in_(scan_ids)))
    await session.execute(delete(ScanEvent).where(ScanEvent.scan_run_id == run_id))
    await session.execute(delete(Scan).where(Scan.scan_run_id == run_id))
    # Shadow rows ONLY — a canonical public row has owner_run_id IS NULL.
    await session.execute(delete(CatalogItem).where(CatalogItem.owner_run_id == run_id))
    await session.execute(delete(UploadFile).where(UploadFile.scan_run_id == run_id))
    await session.delete(run)
    await session.flush()


def serialize_findings(findings: Iterable[Finding]) -> list[dict[str, object]]:
    """Slim public-API representation of finding rows for the report endpoint."""
    out: list[dict[str, object]] = []
    for f in findings:
        out.append(
            {
                "id": str(f.id),
                "rule_id": f.rule_id,
                "severity": f.severity,
                "sub_score": f.sub_score,
                "penalty": f.penalty,
                "status_at_scan": f.status_at_scan,
                "file_path": f.file_path,
                "line_start": f.line_start,
                "line_end": f.line_end,
                "matched_content_sha256": f.matched_content_sha256,
                "remediation_link": f.remediation_link,
                "rubric_version": f.rubric_version,
            }
        )
    return out
