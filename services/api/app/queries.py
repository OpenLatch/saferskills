"""Shared aggregate queries over the catalog + scan tables.

Extracted so the catalog facets endpoint (`routers/items.py`) and the homepage
stats endpoint (`routers/stats.py`) compute identical numbers from one place
rather than duplicating SQL.

"Completed" scan = a scan whose `tier` is not ``unscoped``. Pending rows are
inserted with `tier='unscoped'`, `aggregate_score=0`, `latency_ms=0`
(`scan.persistence._placeholder_scan`); the engine always assigns a real tier
(green/yellow/orange/red) on completion. Filtering on `tier != 'unscoped'` is
therefore the single, schema-honest definition of "completed".
"""

from __future__ import annotations

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.catalog_item import CatalogItem
from app.models.item_source import ItemSource
from app.models.scan import Scan

_UNSCOPED = "unscoped"


async def count_catalog_total(session: AsyncSession) -> int:
    """Non-archived catalog item count."""
    return int(
        (
            await session.execute(
                select(func.count(CatalogItem.id)).where(CatalogItem.archived.is_(False))
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
    """Count of items bucketed by the tier of their most-recent scan."""
    latest_per_item = (
        select(Scan.catalog_item_id, func.max(Scan.scanned_at).label("max_scanned_at"))
        .group_by(Scan.catalog_item_id)
        .subquery()
    )
    rows = (
        await session.execute(
            select(Scan.tier, func.count(Scan.id))
            .join(
                latest_per_item,
                and_(
                    Scan.catalog_item_id == latest_per_item.c.catalog_item_id,
                    Scan.scanned_at == latest_per_item.c.max_scanned_at,
                ),
            )
            .group_by(Scan.tier)
        )
    ).all()
    return {tier: int(count) for tier, count in rows}


async def median_completed_score(session: AsyncSession) -> int | None:
    """Median (P50) aggregate score over completed scans. None when empty."""
    value = (
        await session.execute(
            select(func.percentile_cont(0.5).within_group(Scan.aggregate_score.asc())).where(
                Scan.tier != _UNSCOPED
            )
        )
    ).scalar_one_or_none()
    return round(value) if value is not None else None


async def latency_stats_ms(session: AsyncSession) -> tuple[int | None, int | None]:
    """(p95, avg) latency in ms over completed scans. (None, None) when empty."""
    row = (
        await session.execute(
            select(
                func.percentile_cont(0.95).within_group(Scan.latency_ms.asc()),
                func.avg(Scan.latency_ms),
            ).where(Scan.tier != _UNSCOPED)
        )
    ).first()
    if row is None:
        return None, None
    p95, avg = row
    return (
        round(p95) if p95 is not None else None,
        round(avg) if avg is not None else None,
    )
