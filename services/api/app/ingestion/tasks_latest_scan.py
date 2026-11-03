"""latest_scan_backfill — fills `catalog_items.latest_scan_*` for existing rows.

Migration 0027 adds the columns empty, and every scan writer keeps them current from
then on (`app/scan/persistence.py::refresh_latest_scan`). This fills the rows that
predate the columns. It stays scheduled as a safety net: it only looks at rows with
no latest scan, and a row with nothing to fill is not written.

Check it has finished, before switching any read to the columns:

    SELECT count(*) FROM catalog_items c
    WHERE c.latest_scan_id IS NULL
      AND EXISTS (SELECT 1 FROM scans s
                  WHERE s.catalog_item_id = c.id AND s.tier <> 'unscoped');
"""

from __future__ import annotations

import asyncio
from uuid import UUID

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.ingestion import PERIODIC_MAINTENANCE_PRIORITY, procrastinate_app
from app.scan.persistence import refresh_latest_scan

logger = structlog.get_logger(__name__)

_BATCH = 5_000
_PAUSE_S = 0.5

_NEXT_BATCH_SQL = text("""
    SELECT id FROM catalog_items
    WHERE latest_scan_id IS NULL AND id > :after
    ORDER BY id
    LIMIT :batch
""")


async def backfill_latest_scan(
    session: AsyncSession, *, batch: int = _BATCH, pause_s: float = _PAUSE_S
) -> int:
    """Walk rows with no latest scan by primary key, one committed batch at a time.
    Returns the number of rows filled. Pauses only after a batch that wrote something,
    so the steady-state pass over never-scanned items stays quick."""
    after = UUID(int=0)
    filled = 0
    while True:
        ids: list[UUID] = list(
            (await session.execute(_NEXT_BATCH_SQL, {"after": after, "batch": batch}))
            .scalars()
            .all()
        )
        if not ids:
            break
        written = await refresh_latest_scan(session, ids)
        await session.commit()
        filled += written
        after = ids[-1]
        if written:
            await asyncio.sleep(pause_s)
    logger.info("latest_scan_backfill.done", filled=filled)
    return filled


@procrastinate_app.periodic(cron="20 * * * *")
@procrastinate_app.task(
    name="latest_scan_backfill",
    queue="periodic",
    queueing_lock="latest_scan_backfill_lock",
    priority=PERIODIC_MAINTENANCE_PRIORITY,
)
async def latest_scan_backfill(timestamp: int) -> dict[str, int]:
    from app.db.session import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        return {"filled": await backfill_latest_scan(session)}
