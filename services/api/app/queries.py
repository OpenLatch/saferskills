"""Shared aggregate queries over the catalog + scan tables.

Extracted so the catalog facets endpoint (`routers/items.py`) and the homepage
stats endpoint (`routers/stats.py`) compute identical numbers from one place
rather than duplicating SQL.

Per-item scan numbers read `catalog_items.latest_scan_*`, never `scans`, which is too
large to aggregate per request. See `scan.persistence.refresh_latest_scan`.
"""

from __future__ import annotations

from sqlalchemy import asc, desc, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.catalog_item import CatalogItem
from app.models.item_source import ItemSource
from app.models.scan import Scan
from app.models.scan_run import ScanRun

# Newest scan first. Scans sharing a timestamp put the lower score first, so a tie
# never hides a worse result, then id for a stable order. Matches the ORDER BY in
# `scan.persistence._REFRESH_LATEST_SCAN_SQL`, so an item page and the catalog list
# pick the same scan.
NEWEST_SCAN_FIRST = (desc(Scan.scanned_at), asc(Scan.aggregate_score), desc(Scan.id))

# The predicate of the catalog's partial list indexes (migration 0027). It has to be
# this literal text: SQLAlchemy's `.is_(False)` renders `archived IS false`, which
# Postgres doesn't treat as implying the index's `archived = false`, so the query would
# fall back to a seq scan and sort.
LISTED_ITEM = text("catalog_items.archived = false AND catalog_items.visibility = 'public'")


async def count_catalog_total(session: AsyncSession) -> int:
    """Non-archived, public catalog item count (unlisted shadows excluded)."""
    return int(
        (
            await session.execute(
                select(func.count(CatalogItem.id)).where(
                    CatalogItem.archived.is_(False), CatalogItem.visibility == "public"
                )
            )
        ).scalar_one()
    )


async def count_distinct_registries(session: AsyncSession) -> int:
    """Number of distinct registries any item is sourced from."""
    return int(
        (
            await session.execute(select(func.count(func.distinct(ItemSource.registry_id))))
        ).scalar_one()
    )


async def latest_scan_tier_distribution(session: AsyncSession) -> dict[str, int]:
    """Count of public items by the tier of their latest completed scan. Items with
    no completed scan aren't counted."""
    rows = (
        await session.execute(
            select(CatalogItem.latest_scan_tier, func.count(CatalogItem.id))
            .where(CatalogItem.visibility == "public", CatalogItem.latest_scan_tier.is_not(None))
            .group_by(CatalogItem.latest_scan_tier)
        )
    ).all()
    return {str(tier): int(count) for tier, count in rows}


async def median_completed_score(session: AsyncSession) -> int | None:
    """Median (P50) of each public item's latest completed score. None when empty."""
    value = (
        await session.execute(
            select(
                func.percentile_cont(0.5).within_group(CatalogItem.latest_scan_score.asc())
            ).where(CatalogItem.visibility == "public", CatalogItem.latest_scan_score.is_not(None))
        )
    ).scalar_one_or_none()
    return round(value) if value is not None else None


async def latency_stats_ms(session: AsyncSession) -> tuple[int | None, int | None]:
    """(p95, avg) latency in ms over completed repo scans. (None, None) when empty.

    Latency is the wall-clock of a whole repo scan, recorded on `scan_runs` —
    per-capability `scans` rows carry `latency_ms=0` (the run is the timed unit),
    so this measures `scan_runs`, not the fanned-out per-capability scans.
    """
    row = (
        await session.execute(
            select(
                func.percentile_cont(0.95).within_group(ScanRun.latency_ms.asc()),
                func.avg(ScanRun.latency_ms),
            ).where(ScanRun.status == "completed", ScanRun.visibility == "public")
        )
    ).first()
    if row is None:
        return None, None
    p95, avg = row
    return (
        round(p95) if p95 is not None else None,
        round(avg) if avg is not None else None,
    )
