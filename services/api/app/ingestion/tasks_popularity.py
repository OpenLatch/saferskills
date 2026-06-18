"""popularity_recompute — nightly (02:00 UTC) + on-add.

Runs in the in-process Procrastinate worker (advisory lock 0x5AFE5C13 guards the
worker; `queueing_lock` serialises this task). Every SELECT/UPDATE hard-filters
`source_kind='github' AND visibility='public'` — uploaded artifacts + unlisted
shadow rows are never ranked (G-uploads invariant).

Writes three columns on each public-github capability:
  - popularity_score      (pre-existing int 0-100; we scale the [0,1] formula score)
  - popularity_breakdown  (Phase-A jsonb; per-term transparency)
  - popularity_rank_tier  (Phase-A enum top500/top5k/long_tail; rank-based)

popularity_rank_tier is DISTINCT from the pre-existing popularity_tier scan-tier
(indexed/lite/deep/on_demand), which this task never touches.

`recompute_all` / `recompute_one` are the testable session-taking entry points; the
Procrastinate tasks just wrap them in an AsyncSessionLocal.
"""

from __future__ import annotations

import datetime as dt
import json
from typing import Any

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.ingestion import PERIODIC_MAINTENANCE_PRIORITY, procrastinate_app
from app.ingestion.popularity import compute_popularity_score, get_active_weights

logger = structlog.get_logger(__name__)

_BATCH = 500

# Scalar-extraction projection: pull popularity inputs straight out of the
# metadata jsonb as typed scalars (avoids deserialising the whole blob + the
# asyncpg jsonb-as-text pitfall). pushed_at is a real column since migration 0010.
_COLS = """id,
           COALESCE((metadata->>'stars')::int, 0)                        AS stars,
           COALESCE((metadata->>'star_velocity_7d')::float, 0)           AS velocity,
           COALESCE((metadata->>'weekly_downloads')::int, 0)             AS downloads,
           COALESCE((metadata->>'cross_registry_listing_count')::int, 0) AS cross_reg,
           pushed_at"""
_PUBLIC_GITHUB = "archived = false AND source_kind = 'github' AND visibility = 'public'"

_SELECT_BATCH = text(
    f"SELECT {_COLS} FROM catalog_items WHERE {_PUBLIC_GITHUB} "
    "ORDER BY id LIMIT :limit OFFSET :offset"
)
_SELECT_ONE = text(f"SELECT {_COLS} FROM catalog_items WHERE id = :id AND {_PUBLIC_GITHUB}")

_UPDATE_ONE = text("""
    UPDATE catalog_items
    SET popularity_score = :score,
        popularity_breakdown = CAST(:breakdown AS jsonb),
        updated_at = now()
    WHERE id = :id
""")


async def _denominator_maxes(session: AsyncSession) -> Any:
    return (
        await session.execute(
            text("""
        SELECT
            COALESCE(MAX((metadata->>'stars')::int), 1)              AS max_stars,
            COALESCE(MAX((metadata->>'star_velocity_7d')::float), 1) AS max_velocity,
            COALESCE(MAX((metadata->>'weekly_downloads')::int), 1)   AS max_downloads
        FROM catalog_items
        WHERE archived = false
          AND source_kind = 'github' AND visibility = 'public'
    """)
        )
    ).one()


def _days_since(pushed_at: dt.datetime | None) -> int | None:
    if pushed_at is None:
        return None
    return (dt.datetime.now(tz=dt.UTC) - pushed_at).days


def _score_row(row: Any, weights: Any, maxes: Any) -> tuple[int, str]:
    score, breakdown = compute_popularity_score(
        weights=weights,
        stars=int(row.stars),
        star_velocity_7d=float(row.velocity),
        weekly_downloads=int(row.downloads),
        cross_registry_count=int(row.cross_reg),
        days_since_pushed=_days_since(row.pushed_at),
        max_stars=int(maxes.max_stars),
        max_velocity=float(maxes.max_velocity),
        max_downloads=int(maxes.max_downloads),
    )
    return round(score * 100), json.dumps(breakdown)


async def recompute_all(session: AsyncSession) -> dict[str, Any]:
    """Recompute score + breakdown + rank tiers for every public-github capability."""
    from app.observability.events import emit_popularity_recompute_completed

    weights = await get_active_weights(session)
    maxes = await _denominator_maxes(session)

    pre = (
        (
            await session.execute(
                text("""
        SELECT id FROM catalog_items
        WHERE archived = false AND quality_tier IN ('high','medium')
          AND source_kind = 'github' AND visibility = 'public'
        ORDER BY popularity_score DESC NULLS LAST
        LIMIT 500
    """)
            )
        )
        .scalars()
        .all()
    )
    pre_set = set(pre)

    offset = 0
    total_updated = 0
    while True:
        rows = (await session.execute(_SELECT_BATCH, {"limit": _BATCH, "offset": offset})).all()
        if not rows:
            break
        params: list[dict[str, Any]] = []
        for r in rows:
            score, breakdown = _score_row(r, weights, maxes)
            params.append({"score": score, "breakdown": breakdown, "id": r.id})
        # One executemany per batch (pipelined) rather than a round-trip per row.
        await session.execute(_UPDATE_ONE, params)
        await session.commit()
        total_updated += len(rows)
        offset += _BATCH

    await _assign_rank_tiers(session)
    await session.commit()

    post = (
        (
            await session.execute(
                text("SELECT id FROM catalog_items WHERE popularity_rank_tier = 'top500'")
            )
        )
        .scalars()
        .all()
    )
    changed = len(pre_set.symmetric_difference(set(post)))
    emit_popularity_recompute_completed(top500_changed_count=changed)
    logger.info("popularity_recompute.done", total_updated=total_updated, top500_changed=changed)
    return {"total_updated": total_updated, "top500_changed": changed}


async def recompute_one(session: AsyncSession, catalog_item_id: str) -> dict[str, Any]:
    """Recompute one public-github capability's score+breakdown (no re-ranking)."""
    weights = await get_active_weights(session)
    maxes = await _denominator_maxes(session)
    row = (await session.execute(_SELECT_ONE, {"id": catalog_item_id})).one_or_none()
    if row is None:
        return {"updated": 0}
    score, breakdown = _score_row(row, weights, maxes)
    await session.execute(_UPDATE_ONE, {"score": score, "breakdown": breakdown, "id": row.id})
    await session.commit()
    return {"updated": 1}


async def _assign_rank_tiers(session: AsyncSession) -> None:
    """Re-bucket popularity_rank_tier by rank among public-github high/medium rows."""
    await session.execute(
        text("""
        UPDATE catalog_items SET popularity_rank_tier = 'top500'
        WHERE id IN (
            SELECT id FROM catalog_items
            WHERE archived = false AND quality_tier IN ('high','medium')
              AND source_kind = 'github' AND visibility = 'public'
            ORDER BY popularity_score DESC NULLS LAST
            LIMIT 500
        )
    """)
    )
    await session.execute(
        text("""
        UPDATE catalog_items SET popularity_rank_tier = 'top5k'
        WHERE popularity_rank_tier IS DISTINCT FROM 'top500'
          AND id IN (
            SELECT id FROM catalog_items
            WHERE archived = false AND quality_tier IN ('high','medium')
              AND source_kind = 'github' AND visibility = 'public'
              AND popularity_rank_tier IS DISTINCT FROM 'top500'
            ORDER BY popularity_score DESC NULLS LAST
            LIMIT 4500
        )
    """)
    )
    await session.execute(
        text("""
        UPDATE catalog_items SET popularity_rank_tier = 'long_tail'
        WHERE source_kind = 'github' AND visibility = 'public'
          AND popularity_rank_tier NOT IN ('top500','top5k')
    """)
    )


@procrastinate_app.periodic(cron="0 2 * * *")
@procrastinate_app.task(
    name="popularity_recompute",
    queue="periodic",
    queueing_lock="popularity_recompute_lock",
    priority=PERIODIC_MAINTENANCE_PRIORITY,
)
async def popularity_recompute(timestamp: int) -> dict[str, Any]:
    from app.db.session import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        return await recompute_all(session)


@procrastinate_app.task(name="recompute_one_item", queue="periodic", retry=3)
async def recompute_one_item(catalog_item_id: str) -> dict[str, Any]:
    """On-add lightweight recompute for a single new public-github capability."""
    from app.db.session import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        return await recompute_one(session, catalog_item_id)
