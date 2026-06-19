"""MergeEngine — merges normalized items into catalog_items.

Per migration 0007, one catalog_item = one capability. The repo-level fetch
coordinate (github_org, github_repo) is NOT the upsert key — the per-capability
slug `<org>--<repo>--<kind>-<name>[-<hash6>]` is (delegated to
app.scan.persistence.capability_slug so ingestion + the scan engine mint identical
slugs). Several capabilities share one github_url (UNIQUE(github_url) dropped in
0007). Ingestion-written rows set source_kind='github', visibility='public'.

Contracts:
  - dedup: per-capability slug auto-merge ONLY; no GitHub URL → fuzzy queue.
  - conflict: GitHub always wins (other sources fill blanks, never override).
  - agent_compatibility: classifier writes the EXISTING column (0003).
  - quality_tier: soft gate. Set on insert; RE-tiered on update only when
    the incoming item carries enrichment signals (`_has_enrichment_signals`) so a
    re-crawl that enriches (e.g. mcp_registry) heals rows first ingested without
    repo signals. A signal-less update never downgrades a tiered row.

Returns: 'added' | 'updated' | 'added_with_merge_candidate'.
"""

from __future__ import annotations

import datetime as dt
import json
import uuid
from typing import Any

import structlog
from rapidfuzz import fuzz
from rapidfuzz.distance import JaroWinkler
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.ingestion.framework.base_adapter import NormalizedItem
from app.ingestion.framework.classifier import classify_all
from app.models import Author, CatalogItem, ItemSource
from app.scan.fetch import GithubRef
from app.scan.persistence import capability_slug

logger = structlog.get_logger(__name__)

_FUZZY_TRGM_PREFILTER = 0.6
_RAPIDFUZZ_THRESHOLD = 85.0
_JARO_WINKLER_THRESHOLD = 90.0  # percent

# Concurrent cycles crawl overlapping repos and race on the same capability slug;
# the insert path retries a bounded number of times on a PG deadlock (40P01).
_MAX_UPSERT_ATTEMPTS = 3
_PG_DEADLOCK_SQLSTATE = "40P01"


def _is_deadlock(exc: DBAPIError) -> bool:
    """True for a Postgres deadlock_detected (SQLSTATE 40P01)."""
    orig = getattr(exc, "orig", None)
    code = getattr(orig, "sqlstate", None) or getattr(orig, "pgcode", None)
    return code == _PG_DEADLOCK_SQLSTATE


def _now() -> dt.datetime:
    return dt.datetime.now(tz=dt.UTC)


_LICENSE_SPDX_MAX = 100  # catalog_items.license_spdx is VARCHAR(100)


def _clamp_license(value: str | None) -> str | None:
    """Defensive backstop for the VARCHAR(100) license column.

    Adapters are responsible for extracting a short SPDX id, but `license` is
    free-form upstream data we don't fully control (PyPI's field can hold the whole
    license body). Reduce to the first line + cap so a pathological value can never
    abort an ingestion cycle. Belt-and-suspenders to the per-adapter extraction.
    """
    if not value:
        return None
    first = value.strip().splitlines()[0].strip() if value.strip() else ""
    return first[:_LICENSE_SPDX_MAX] or None


def _has_enrichment_signals(n: NormalizedItem) -> bool:
    """True when the incoming item carries repo signals an `enrich()` pass fetched
    (manifest/README bytes, stars, or a commit-count proxy).

    Gates re-tiering on update: only a source that actually fetched repo facts may
    recompute `quality_tier`. A bare/aggregator update with no signals must never
    downgrade a well-tiered row back to `empty` (the soft gate)."""
    return bool(n.metadata_files) or n.stars is not None or bool(n.payload_hint.get("commit_count"))


def _capability_slug(n: NormalizedItem, kind: str) -> str | None:
    """Per-capability slug, or None when the GitHub coordinate is missing."""
    if not n.github_org or not n.github_repo:
        return None
    return capability_slug(GithubRef(org=n.github_org, repo=n.github_repo), kind, n.display_name)


def _source_entry(registry_id: str, registry_url: str | None) -> dict[str, Any]:
    now_iso = _now().isoformat()
    return {
        "registryId": registry_id,
        "registryUrl": registry_url or "",
        "firstIndexedAt": now_iso,
        "lastSeenAt": now_iso,
    }


class MergeEngine:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def upsert(self, n: NormalizedItem, *, raw_hash: str, source: str) -> str:
        kind = n.kind or classify_all(n)[0]
        slug = _capability_slug(n, kind)
        if slug is None:
            return await self._maybe_queue_fuzzy(n, source)
        return await self._upsert_by_slug(n, slug=slug, raw_hash=raw_hash, source=source)

    async def _select_by_slug(self, slug: str) -> CatalogItem | None:
        return (
            await self.session.execute(select(CatalogItem).where(CatalogItem.slug == slug))
        ).scalar_one_or_none()

    async def _upsert_by_slug(
        self, n: NormalizedItem, *, slug: str, raw_hash: str, source: str
    ) -> str:
        """Concurrency-safe per-capability upsert.

        The aggregators crawl overlapping GitHub repos, so several cycles running
        in the same worker can race to insert the SAME capability slug. A plain
        SELECT-then-INSERT then loses the race with `duplicate key … uq_catalog_
        items_slug`, and two batches inserting overlapping slugs in different order
        DEADLOCK on the unique index — either way the whole cycle's batch aborts.

        Fix: do the INSERT inside a SAVEPOINT so a collision can't poison the batch
        transaction. A unique-violation means a peer committed the same slug between
        our SELECT and INSERT → re-read it and take the (idempotent, source-
        re-attributing) UPDATE path. A deadlock is the expected-under-concurrency
        case Postgres tells us to retry — the savepoint rollback keeps the batch
        alive and the retry's re-SELECT almost always resolves to the peer's
        now-committed row.
        """
        for attempt in range(_MAX_UPSERT_ATTEMPTS):
            existing = await self._select_by_slug(slug)
            if existing is not None:
                await self._apply_update(existing, n, raw_hash=raw_hash, source=source)
                return "updated"
            try:
                # SAVEPOINT so a deadlock (the rare lock-ordering clash between two
                # batches inserting overlapping slugs) rolls back THIS insert only,
                # not the whole cycle's batch — then we retry.
                async with self.session.begin_nested():
                    new_id = await self._insert_new(n, slug=slug, raw_hash=raw_hash, source=source)
            except DBAPIError as exc:
                if _is_deadlock(exc) and attempt < _MAX_UPSERT_ATTEMPTS - 1:
                    logger.warning("merger.upsert_deadlock_retry", slug=slug, attempt=attempt)
                    continue  # savepoint rolled back; re-SELECT + retry the insert
                raise
            if new_id is None:
                # ON CONFLICT DO NOTHING fired: a peer committed this slug first
                # (the INSERT waited for the peer's txn, so the row is now visible).
                existing = await self._select_by_slug(slug)
                if existing is None:
                    continue  # peer rolled back — retry the insert
                await self._apply_update(existing, n, raw_hash=raw_hash, source=source)
                return "updated"
            await self._defer_on_add_recompute(new_id)
            # Index → scan: a brand-new public-github capability is enqueued for an
            # immediate durable scan (the reconciliation drainer is the steady-state
            # guarantee; this just makes a fresh arrival scan promptly).
            await self._defer_on_add_scan(n.github_url)
            return "added"
        # Only reached if every attempt deadlocked — let the cycle's retry take it.
        raise RuntimeError(f"upsert exhausted retries for slug {slug!r}")

    async def _defer_on_add_scan(self, github_url: str | None) -> None:
        """Best-effort defer of a durable `scan_capability_repo` job on a new item
        or a content-hash change. The `queueing_lock` dedups against in-flight jobs
        (the reconciliation drainer + this hook can't double-enqueue). A defer
        failure (e.g. the Procrastinate app isn't open in a unit test) must never
        break the upsert — the reconciliation drainer is the steady-state net."""
        if not github_url:
            return
        # Honor the auto-scan kill-switch: SCAN_AUTOSCAN_ENABLED=false pauses ALL
        # bulk scanning, including this on-ingest hook (documented in
        # environment-config.md + ingestion.md § Durable auto-scan pipeline). The
        # reconciliation drainer already gates on this; without the same gate here
        # every freshly-ingested item still enqueues a scan job behind the flag.
        from app.core.config import get_settings

        if not get_settings().scan_autoscan_enabled:
            return
        try:
            from app.ingestion.tasks_scan import defer_scan_job

            await defer_scan_job(github_url, reason="ingest")
        except Exception:
            logger.debug("merger.on_add_scan_defer_skipped", github_url=github_url)

    async def _defer_on_add_recompute(self, catalog_item_id: uuid.UUID) -> None:
        """On-add lightweight popularity recompute for the new public-github row.
        Best-effort: the nightly `popularity_recompute` is the real
        guarantee, so a defer failure (e.g. the Procrastinate app isn't open in a
        unit test) must never break the upsert."""
        try:
            from app.ingestion.tasks_popularity import recompute_one_item

            await recompute_one_item.defer_async(catalog_item_id=str(catalog_item_id))
        except Exception:
            logger.debug(
                "merger.on_add_recompute_defer_skipped", catalog_item_id=str(catalog_item_id)
            )

    async def _insert_new(
        self, n: NormalizedItem, *, slug: str, raw_hash: str, source: str
    ) -> uuid.UUID | None:
        """Insert a brand-new capability row, or return None if a peer beat us to it.

        Uses INSERT … ON CONFLICT (slug) DO NOTHING, NOT a plain INSERT: the
        aggregators crawl overlapping repos, so concurrent cycles race on the same
        slug. A plain INSERT loses that race with a `duplicate key … uq_catalog_
        items_slug` violation that Postgres LOGS as an ERROR even when the app
        catches it — flooding the DB log during a crawl. ON CONFLICT DO NOTHING
        instead waits for the peer's txn then cleanly no-ops (no violation, no
        log); a NULL `returning` id signals the conflict so the caller re-reads +
        takes the (idempotent, source-re-attributing) UPDATE path.
        """
        ckind, kind_signals, quality_tier, quality_signals, agents = classify_all(n)
        # Honor the adapter's declared kind (contract: "classifier finalises when
        # None") so the stored column matches the slug, which upsert() built from
        # the same hint. classify_all already resolved agents against n.kind.
        kind = n.kind or ckind
        now = _now()
        values: dict[str, Any] = {
            "kind": kind,
            "slug": slug,
            "display_name": n.display_name[:200],
            "github_url": n.github_url,
            "github_org": n.github_org,
            "github_repo": n.github_repo,
            "default_branch": n.default_branch or "main",
            "popularity_tier": "indexed",
            "popularity_score": 0,
            "popularity_rank_tier": "long_tail",
            "agent_compatibility": agents,
            "quality_tier": quality_tier,
            "quality_signals": quality_signals,
            "kind_signals": kind_signals,
            "availability": "archived" if (n.repo_archived or n.repo_yanked) else "available",
            "archived": bool(n.repo_archived or n.repo_yanked),
            "source_kind": "github",
            "visibility": "public",
            "content_hash_sha256": raw_hash,
            "consecutive404_count": 0,
            "last_seen200_at": now,
            "pushed_at": _parse_dt(n.pushed_at),
            "github_stars": n.stars,
            "license_spdx": _clamp_license(n.license_spdx),
            "popularity_breakdown": {},
            "sources": [_source_entry(source, n.source_url)],
            "item_metadata": {
                "description": n.description,
                "license_spdx": _clamp_license(n.license_spdx),
                "stars": n.stars,
                "weekly_downloads": n.weekly_downloads,
                "pushed_at": n.pushed_at,
                "github_username": n.github_org,
                "conflicts": [],
            },
            "created_at": now,
            "updated_at": now,
        }
        stmt = (
            pg_insert(CatalogItem)
            .values(**values)
            .on_conflict_do_nothing(index_elements=["slug"])
            .returning(CatalogItem.id)
        )
        new_id = (await self.session.execute(stmt)).scalar_one_or_none()
        if new_id is None:
            return None  # a concurrent cycle inserted this slug first
        await self._upsert_item_source(new_id, source, n.source_url)
        await self._upsert_author(n)
        return new_id

    async def _apply_update(
        self, existing: CatalogItem, n: NormalizedItem, *, raw_hash: str, source: str
    ) -> None:
        is_github = source in {"github_skills", "github_topics"}
        meta = dict(existing.item_metadata or {})
        conflicts: list[dict[str, Any]] = list(meta.get("conflicts") or [])

        for field in ("description", "license_spdx"):
            incoming = getattr(n, field, None)
            current = meta.get(field)
            if incoming is not None and incoming != current:
                if current is None:
                    meta[field] = incoming  # fill a blank — any source may
                elif is_github:
                    conflicts.append(
                        {
                            "field": field,
                            "from": current,
                            "to": incoming,
                            "chosen": "github",
                            "source": source,
                        }
                    )
                    meta[field] = incoming  # GitHub wins
                else:
                    conflicts.append(
                        {
                            "field": field,
                            "from": current,
                            "to": incoming,
                            "chosen": "current",
                            "source": source,
                        }
                    )

        if is_github:
            if n.stars is not None:
                meta["stars"] = n.stars
                existing.github_stars = n.stars
            if n.pushed_at is not None:
                meta["pushed_at"] = n.pushed_at
                existing.pushed_at = _parse_dt(n.pushed_at)
            if n.weekly_downloads is not None:
                meta["weekly_downloads"] = n.weekly_downloads
            if n.license_spdx is not None and existing.license_spdx is None:
                existing.license_spdx = _clamp_license(n.license_spdx)

        if existing.content_hash_sha256 != raw_hash:
            meta["last_hash_change_at"] = _now().isoformat()
            # Content drift → enqueue a durable re-scan (the scan job's own
            # conditional-fetch gate confirms the change before doing real work;
            # queueing_lock dedups against the reconciliation drainer).
            await self._defer_on_add_scan(existing.github_url)

        # Re-tier from fresh enrichment so a re-crawl heals rows ingested before the
        # source learned to enrich (e.g. the mcp_registry backfill — its cursor-based
        # feed only re-yields a server on a reset). Gated to items that actually
        # carry repo signals so a bare update never downgrades a tiered row.
        if _has_enrichment_signals(n):
            _ckind, kind_signals, quality_tier, quality_signals, _agents = classify_all(n)
            existing.quality_tier = quality_tier
            existing.quality_signals = quality_signals
            existing.kind_signals = kind_signals
            if n.stars is not None:
                existing.github_stars = n.stars
                meta["stars"] = n.stars
            if n.pushed_at is not None:
                existing.pushed_at = _parse_dt(n.pushed_at)
                meta["pushed_at"] = n.pushed_at

        meta["conflicts"] = conflicts
        existing.item_metadata = meta
        existing.content_hash_sha256 = raw_hash
        existing.last_seen200_at = _now()
        existing.consecutive404_count = 0
        existing.availability = "archived" if (n.repo_archived or n.repo_yanked) else "available"
        if n.repo_archived or n.repo_yanked:
            existing.archived = True
        existing.sources = _merge_source_array(existing.sources, source, n.source_url)
        existing.updated_at = _now()

        await self._upsert_item_source(existing.id, source, n.source_url)
        await self._upsert_author(n)

    async def _maybe_queue_fuzzy(self, n: NormalizedItem, source: str) -> str:
        """No GitHub coordinate → stage the row + queue fuzzy candidates."""
        rows = (
            await self.session.execute(
                text(
                    "SELECT id, display_name FROM catalog_items "
                    "WHERE similarity(display_name, :name) > :pre AND archived = false LIMIT 20"
                ).bindparams(name=n.display_name, pre=_FUZZY_TRGM_PREFILTER)
            )
        ).fetchall()

        high: list[tuple[uuid.UUID, float, float]] = []
        for row in rows:
            score = float(fuzz.token_set_ratio(n.display_name, row.display_name))
            jw = float(JaroWinkler.normalized_similarity(n.display_name, row.display_name) * 100)
            if score >= _RAPIDFUZZ_THRESHOLD or jw >= _JARO_WINKLER_THRESHOLD:
                high.append((row.id, score, jw))

        staged_id = await self._insert_staging_row(n, source)
        if not high:
            return "added"

        for other_id, score, jw in high:
            left_id, right_id = sorted([staged_id, other_id], key=str)
            await self.session.execute(
                text(
                    "INSERT INTO merge_candidates "
                    "(left_artifact_id, right_artifact_id, rapidfuzz_score, jaro_winkler_score, signals, status) "
                    "VALUES (CAST(:l AS uuid), CAST(:r AS uuid), :s, :jw, CAST(:sig AS jsonb), 'pending') "
                    "ON CONFLICT (left_artifact_id, right_artifact_id) DO NOTHING"
                ).bindparams(
                    l=str(left_id),
                    r=str(right_id),
                    s=score,
                    jw=jw,
                    sig=json.dumps(
                        {"name": True, "source": source, "incoming_name": n.display_name}
                    ),
                )
            )
        return "added_with_merge_candidate"

    async def _insert_staging_row(self, n: NormalizedItem, source: str) -> uuid.UUID:
        ckind, kind_signals, _qt, quality_signals, agents = classify_all(n)
        kind = n.kind or ckind  # honor the adapter hint (see _insert_new)
        now = _now()
        item = CatalogItem(
            kind=kind,
            slug=f"pending--{uuid.uuid4().hex[:8]}",
            display_name=n.display_name[:200],
            github_url=n.github_url,
            github_org=n.github_org,
            github_repo=n.github_repo,
            default_branch=n.default_branch or "main",
            popularity_tier="indexed",
            popularity_score=0,
            popularity_rank_tier="long_tail",
            agent_compatibility=agents,
            quality_tier="low",  # un-disambiguated → hidden from default catalog
            quality_signals=quality_signals,
            kind_signals=kind_signals,
            availability="available",
            archived=False,
            source_kind="github",
            visibility="public",
            consecutive404_count=0,
            sources=[_source_entry(source, n.source_url)],
            item_metadata={"pending_merge": True, "discovered_via": source},
            created_at=now,
            updated_at=now,
        )
        self.session.add(item)
        await self.session.flush()
        await self._upsert_item_source(item.id, source, n.source_url)
        return item.id

    async def _upsert_item_source(
        self, catalog_item_id: uuid.UUID, source: str, source_url: str | None
    ) -> None:
        stmt = (
            pg_insert(ItemSource)
            .values(
                catalog_item_id=catalog_item_id,
                registry_id=source,
                registry_url=source_url or "",
                status="active",
            )
            .on_conflict_do_update(
                index_elements=["catalog_item_id", "registry_id"],
                set_={"last_seen_at": _now(), "status": "active"},
            )
        )
        await self.session.execute(stmt)

    async def _upsert_author(self, n: NormalizedItem) -> None:
        if not n.github_org:
            return
        stmt = (
            pg_insert(Author)
            .values(github_username=n.github_org)
            .on_conflict_do_update(
                index_elements=["github_username"], set_={"last_seen_at": _now()}
            )
        )
        await self.session.execute(stmt)


def _parse_dt(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    try:
        return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _merge_source_array(
    existing: list[dict[str, Any]] | None, registry_id: str, registry_url: str | None
) -> list[dict[str, Any]]:
    arr = list(existing or [])
    now_iso = _now().isoformat()
    for entry in arr:
        if entry.get("registryId") == registry_id:
            entry["lastSeenAt"] = now_iso
            if registry_url and not entry.get("registryUrl"):
                entry["registryUrl"] = registry_url
            return arr
    arr.append(_source_entry(registry_id, registry_url))
    return arr
