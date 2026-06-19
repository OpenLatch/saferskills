"""access_log_retention — daily 04:00 UTC.

The `access_log` writer (`app/core/access_log_middleware.py`) already redacts the
IP to /24 (v4) / /48 (v6) AT WRITE TIME — raw IPs are never stored (privacy.md §
IP redaction). So retention is a straight 30-day row sweep matching privacy.md §
Retention ("rows are swept after 30 days") + security.md Operational tier (30
days). Aggregated rollups (a later reader's job) survive independently of the
row-level store; there is nothing to redact here, only to delete.

`sweep_access_log` is the testable session-taking entry point.
"""

from __future__ import annotations

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.ingestion import PERIODIC_MAINTENANCE_PRIORITY, procrastinate_app

logger = structlog.get_logger(__name__)

_RETENTION_DAYS = 30


async def sweep_access_log(session: AsyncSession, *, days: int = _RETENTION_DAYS) -> int:
    # Count via a CTE wrapper so a large sweep doesn't ship every deleted id over
    # the wire (and `scalar_one` is typed, unlike CursorResult.rowcount).
    deleted = (
        await session.execute(
            text(
                "WITH d AS (DELETE FROM access_log "
                "WHERE ts < now() - make_interval(days => :days) RETURNING 1) "
                "SELECT count(*) FROM d"
            ),
            {"days": days},
        )
    ).scalar_one()
    await session.commit()
    logger.info("access_log_retention.done", deleted=deleted)
    return deleted


@procrastinate_app.periodic(cron="0 4 * * *")
@procrastinate_app.task(
    name="access_log_retention",
    queue="periodic",
    queueing_lock="access_log_retention_lock",
    priority=PERIODIC_MAINTENANCE_PRIORITY,
)
async def access_log_retention(timestamp: int) -> dict[str, int]:
    from app.db.session import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        return {"deleted": await sweep_access_log(session)}
