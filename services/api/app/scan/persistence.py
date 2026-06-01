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
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.artifact_blob import ArtifactBlob
from app.models.catalog_item import CatalogItem
from app.models.scan import Finding, Scan
from app.models.scan_run import ScanRun
from app.scan.engine import CapabilityResult, RepoScanResult, ScanResult
from app.scan.fetch import GithubRef, parse_github_url
from app.services.agent_compat import agent_compatibility_for
from app.services.repository_metadata import RepositoryMetadata, get_repository_metadata

_MANIFEST_MAX_BYTES = 64 * 1024  # cap the stored public manifest at 64 KiB
# Per-file cap on what we store in artifact_blobs (matches the engine's per-file
# fetch cap). Files above this are recorded as present-but-not-stored.
_SNAPSHOT_MAX_PER_FILE_BYTES = 5 * 1024 * 1024


def _looks_binary(content: bytes) -> bool:
    """Null-byte heuristic — a NUL in the first 8 KiB ⇒ treat as binary.

    Cheap and good enough to separate text we line-diff from binaries we only
    record as present (path → null sentinel), without a charset-detection dep.
    """
    return b"\x00" in content[:8192]


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
    # Dedup within this scan before the DB round-trip — identical paths/bytes
    # collapse to one INSERT row, and on_conflict_do_nothing dedups globally.
    new_blobs: dict[str, dict[str, object]] = {}

    for path, content in files_index:
        if _looks_binary(content) or len(content) > _SNAPSHOT_MAX_PER_FILE_BYTES:
            file_map[path] = None
            continue
        sha = hashlib.sha256(content).hexdigest()
        file_map[path] = sha
        if sha not in new_blobs:
            new_blobs[sha] = {
                "sha256": sha,
                "content": content,
                "byte_size": len(content),
                "is_binary": False,
            }

    if new_blobs:
        await session.execute(
            pg_insert(ArtifactBlob).on_conflict_do_nothing(index_elements=["sha256"]),
            list(new_blobs.values()),
        )
    return file_map


def _snapshot_identity(file_map: dict[str, str | None]) -> str:
    """Stable content hash of the whole snapshot (sorted {path: sha} map).

    A single identity for the scanned tree — reuses the dead
    `catalog_items.content_hash_sha256` column and enables future drift
    detection (a changed identity ⇒ the repo's tracked files moved).
    """
    canonical = json.dumps(file_map, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


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
            text = content[:_MANIFEST_MAX_BYTES].decode("utf-8", errors="replace")
            return path, text
    return None


def compute_idempotency_key(github_url: str, ref_sha: str, rubric_version: str) -> str:
    """SHA-256 idempotency key per scan-report.schema.json contract."""
    raw = f"{github_url}|{ref_sha}|{rubric_version}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def slug_for(ref: GithubRef) -> str:
    """`<org>--<repo>` URL-safe slug per I-02 D-15."""
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
) -> None:
    """Fill a (flushed) scan row from an engine result: score, findings, manifest,
    snapshot. Shared by the single-scan and per-capability-run write paths.

    `scan` must already have an `id` (flush before calling). Existing findings
    for the scan are cleared first so a rescan-in-place never double-inserts.
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

        # Persist the per-capability text-file snapshot (deduped) for diffs + zip.
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
    if item is not None:
        # Refresh public GitHub metadata (off the request path, cached ~1h,
        # best-effort — never fail a scan over metadata).
        meta = await get_repository_metadata(item.github_org, item.github_repo)
    await _apply_scan_result(session, scan, result, item=item, meta=meta)
    await session.flush()
    return scan


async def persist_pending_scan_run(
    session: AsyncSession,
    *,
    idempotency_key: str,
    github_url: str,
    rubric_version: str,
    engine_version: str,
    source: str,
) -> ScanRun:
    """Insert the initial `scan_runs` row + return it. Idempotent on the run's
    idempotency_key — this is the id the submit response + SSE channel key on."""
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
    )
    session.add(run)
    await session.flush()
    return run


def _capability_scan_key(run: ScanRun, cap: CapabilityResult) -> str:
    """Stable per-capability idempotency key — keyed on the run URL + the
    capability's (component_path, kind) so a rescan updates the same scan row
    rather than inserting a duplicate. `scans.idempotency_key` is UNIQUE."""
    return compute_idempotency_key(
        f"{run.github_url}#{cap.component_path}#{cap.kind}",
        ref_sha="0" * 40,
        rubric_version=run.rubric_version,
    )


async def persist_completed_scan_run(
    session: AsyncSession,
    run: ScanRun,
    repo_result: RepoScanResult,
) -> ScanRun:
    """Fan out a completed repo scan into N catalog items + N scans, then write
    the repo rollup onto the run.

    Per capability: ensure the catalog item (by slug) → create/reuse its `scans`
    row (`scan_run_id` + `component_path`) → fill score/findings/manifest/snapshot
    via the shared `_apply_scan_result`. The GitHub metadata fetch is hoisted to
    once-per-run and mirrored onto every item. Shared repo-wide blobs (LICENSE,
    …) dedupe via `_capture_snapshot`'s `on_conflict_do_nothing`.
    """
    ref = parse_github_url(run.github_url)
    meta = await get_repository_metadata(ref.org, ref.repo)

    for cap in repo_result.capabilities:
        item = await ensure_capability_item(session, ref, run.github_url, cap)
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
                github_url=run.github_url,
                ref_sha=cap.result.ref_sha,
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
        await _apply_scan_result(session, scan, cap.result, item=item, meta=meta)

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
