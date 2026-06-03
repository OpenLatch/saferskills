"""MergeEngine — merges normalized items into catalog_items.

Per migration 0007, one catalog_item = one capability. The repo-level fetch
coordinate (github_org, github_repo) is NOT the upsert key — the per-capability
slug `<org>--<repo>--<kind>-<name>[-<hash6>]` is (delegated to
app.scan.persistence.capability_slug so ingestion + the scan engine mint identical
slugs). Several capabilities share one github_url (UNIQUE(github_url) dropped in
0007). Ingestion-written rows set source_kind='github', visibility='public'.

Contracts:
  - D-04-09 dedup: per-capability slug auto-merge ONLY; no GitHub URL → fuzzy queue.
  - D-04-11 conflict: GitHub always wins (other sources fill blanks, never override).
  - D-04-31 agent_compatibility: classifier writes the EXISTING column (0003).
  - D-04-19 quality_tier: soft gate.

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


def _now() -> dt.datetime:
    return dt.datetime.now(tz=dt.UTC)


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

        existing = (
            await self.session.execute(select(CatalogItem).where(CatalogItem.slug == slug))
        ).scalar_one_or_none()

        if existing is None:
            new_id = await self._insert_new(n, slug=slug, raw_hash=raw_hash, source=source)
            await self._defer_on_add_recompute(new_id)
            return "added"

        await self._apply_update(existing, n, raw_hash=raw_hash, source=source)
        return "updated"

    async def _defer_on_add_recompute(self, catalog_item_id: uuid.UUID) -> None:
        """On-add lightweight popularity recompute for the new public-github row
        (D-04-13). Best-effort: the nightly `popularity_recompute` is the real
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
    ) -> uuid.UUID:
        kind, kind_signals, quality_tier, quality_signals, agents = classify_all(n)
        now = _now()
        item = CatalogItem(
            kind=kind,
            slug=slug,
            display_name=n.display_name[:200],
            github_url=n.github_url,
            github_org=n.github_org,
            github_repo=n.github_repo,
            default_branch=n.default_branch or "main",
            popularity_tier="indexed",
            popularity_score=0,
            popularity_rank_tier="long_tail",
            agent_compatibility=agents,
            quality_tier=quality_tier,
            quality_signals=quality_signals,
            kind_signals=kind_signals,
            availability="archived" if (n.repo_archived or n.repo_yanked) else "available",
            archived=bool(n.repo_archived or n.repo_yanked),
            source_kind="github",
            visibility="public",
            content_hash_sha256=raw_hash,
            consecutive404_count=0,
            last_seen200_at=now,
            pushed_at=_parse_dt(n.pushed_at),
            github_stars=n.stars,
            license_spdx=n.license_spdx,
            popularity_breakdown={},
            sources=[_source_entry(source, n.source_url)],
            item_metadata={
                "description": n.description,
                "license_spdx": n.license_spdx,
                "stars": n.stars,
                "weekly_downloads": n.weekly_downloads,
                "pushed_at": n.pushed_at,
                "github_username": n.github_org,
                "conflicts": [],
            },
            created_at=now,
            updated_at=now,
        )
        self.session.add(item)
        await self.session.flush()  # assigns item.id
        await self._upsert_item_source(item.id, source, n.source_url)
        await self._upsert_author(n)
        return item.id

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
                existing.license_spdx = n.license_spdx

        if existing.content_hash_sha256 != raw_hash:
            meta["last_hash_change_at"] = _now().isoformat()
            # The top-500 rug-pull alert (D-04-16) was descoped from Phase C; the
            # hash-change timestamp is still recorded here for a future re-scan trigger.

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
        """No GitHub coordinate → stage the row + queue fuzzy candidates (D-04-09)."""
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
        kind, kind_signals, _qt, quality_signals, agents = classify_all(n)
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
