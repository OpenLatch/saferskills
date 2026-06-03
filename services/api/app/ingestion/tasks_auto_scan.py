"""auto_scan_trigger_deep / _lite — enqueue scans for popular capabilities.

Both run in the in-process Procrastinate worker. They select PUBLIC GITHUB
capability rows (uploads + unlisted shadow rows are never auto-scanned) and call
`app.queue.scan_runner.enqueue_scan` — the EXACT on-demand path POST /scans uses
(insert a pending scan_runs row + asyncio.create_task the repo scan). On
completion enqueue_scan stamps `last_<depth>_scan_at`, which these selection
queries read for the recency gate.

`scans.tier` is the trust badge (green/yellow/…), NOT a scan depth — the recency
columns (migration 0012) are the depth-completion record.

D-04-14: top-500 Deep, 30-day cadence, nightly 02:30 UTC (after popularity_recompute).
D-04-15: top-5k Lite, 7-day cadence, hourly, 1h debounce on brand-new arrivals.

`run_trigger` is the testable entry point (the enqueue callable is injected so
tests can assert selection without spawning real scans).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import structlog
from sqlalchemy import TextClause, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.ingestion import procrastinate_app

logger = structlog.get_logger(__name__)

# Bounded per cycle so a nightly/hourly tick can't spawn an unbounded burst of
# concurrent repo scans.
_DEEP_LIMIT = 100
_LITE_LIMIT = 200

EnqueueFn = Callable[..., Awaitable[Any]]

_SELECT_DEEP = text("""
    SELECT id, github_url
    FROM catalog_items
    WHERE popularity_rank_tier = 'top500'
      AND archived = false
      AND source_kind = 'github' AND visibility = 'public'
      AND github_url IS NOT NULL
      AND (last_deep_scan_at IS NULL OR last_deep_scan_at < now() - interval '30 days')
    ORDER BY popularity_score DESC
    LIMIT :limit
""")

_SELECT_LITE = text("""
    SELECT id, github_url
    FROM catalog_items
    WHERE popularity_rank_tier IN ('top500', 'top5k')
      AND archived = false
      AND source_kind = 'github' AND visibility = 'public'
      AND github_url IS NOT NULL
      AND created_at < now() - interval '1 hour'
      AND (last_lite_scan_at IS NULL OR last_lite_scan_at < now() - interval '7 days')
    ORDER BY popularity_score DESC
    LIMIT :limit
""")


async def run_trigger(
    session: AsyncSession,
    *,
    select_stmt: TextClause,
    limit: int,
    depth: str,
    enqueue: EnqueueFn,
) -> int:
    """Select candidate rows + enqueue a scan of `depth` for each. Returns count."""
    rows = (await session.execute(select_stmt, {"limit": limit})).all()
    enqueued = 0
    for r in rows:
        await enqueue(catalog_item_id=str(r.id), github_url=r.github_url, depth=depth)
        enqueued += 1
    return enqueued


@procrastinate_app.periodic(cron="30 2 * * *")  # 30 min after popularity_recompute
@procrastinate_app.task(
    name="auto_scan_trigger_deep", queue="periodic", queueing_lock="auto_scan_trigger_deep_lock"
)
async def auto_scan_trigger_deep(timestamp: int) -> dict[str, int]:
    from app.db.session import AsyncSessionLocal
    from app.queue.scan_runner import enqueue_scan

    async with AsyncSessionLocal() as session:
        enqueued = await run_trigger(
            session, select_stmt=_SELECT_DEEP, limit=_DEEP_LIMIT, depth="deep", enqueue=enqueue_scan
        )
    logger.info("auto_scan_trigger_deep.done", enqueued=enqueued)
    return {"enqueued": enqueued}


@procrastinate_app.periodic(cron="0 * * * *")  # hourly
@procrastinate_app.task(
    name="auto_scan_trigger_lite", queue="periodic", queueing_lock="auto_scan_trigger_lite_lock"
)
async def auto_scan_trigger_lite(timestamp: int) -> dict[str, int]:
    from app.db.session import AsyncSessionLocal
    from app.queue.scan_runner import enqueue_scan

    async with AsyncSessionLocal() as session:
        enqueued = await run_trigger(
            session, select_stmt=_SELECT_LITE, limit=_LITE_LIMIT, depth="lite", enqueue=enqueue_scan
        )
    logger.info("auto_scan_trigger_lite.done", enqueued=enqueued)
    return {"enqueued": enqueued}
