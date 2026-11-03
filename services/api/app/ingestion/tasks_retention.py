"""Daily retention sweeps: `access_log` + finished Procrastinate jobs.

The `access_log` writer (`app/core/access_log_middleware.py`) already redacts the
IP to /24 (v4) / /48 (v6) AT WRITE TIME — raw IPs are never stored (privacy.md §
IP redaction). So retention is a straight 30-day row sweep matching privacy.md §
Retention ("rows are swept after 30 days") + security.md Operational tier (30
days). Aggregated rollups (a later reader's job) survive independently of the
row-level store; there is nothing to redact here, only to delete.

`procrastinate_jobs` is otherwise never purged, and `list_jobs_async(queueing_lock=…)`
seq-scans it on every scan defer, so its size is a per-defer cost. Only `succeeded`
jobs go: `/admin/sources` reads `failed` rows as dead letters. `procrastinate_events`
rows follow by FK cascade, and a delete trigger unlinks `procrastinate_periodic_defers`.

`sweep_access_log` and `sweep_succeeded_jobs` are the testable session-taking entry
points.
"""

from __future__ import annotations

import asyncio

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.ingestion import PERIODIC_MAINTENANCE_PRIORITY, procrastinate_app

logger = structlog.get_logger(__name__)

_RETENTION_DAYS = 30
_JOB_RETENTION_DAYS = 7
_JOB_DELETE_BATCH = 5_000
_JOB_DELETE_PAUSE_S = 0.5

# Not `job_manager.delete_old_jobs`: its single statement sorts the full jobs x events
# join, which is the wrong shape for a loaded database, and the first run has a large
# backlog. Walking the PK in batches keeps each statement short and lets the pause
# give the database room between them.
_DELETE_JOB_BATCH_SQL = text("""
    WITH batch AS (
        SELECT j.id
        FROM procrastinate_jobs j
        WHERE j.status = 'succeeded'
          AND NOT EXISTS (
              SELECT 1 FROM procrastinate_events e
              WHERE e.job_id = j.id AND e.at >= now() - make_interval(days => :days)
          )
        ORDER BY j.id
        LIMIT :batch
    ), deleted AS (
        DELETE FROM procrastinate_jobs j USING batch WHERE j.id = batch.id RETURNING 1
    )
    SELECT count(*) FROM deleted
""")


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


async def sweep_succeeded_jobs(
    session: AsyncSession,
    *,
    days: int = _JOB_RETENTION_DAYS,
    batch: int = _JOB_DELETE_BATCH,
    pause_s: float = _JOB_DELETE_PAUSE_S,
) -> int:
    """Delete `succeeded` jobs with no event newer than `days`, one committed batch
    at a time. Returns the number of jobs deleted."""
    total = 0
    while True:
        deleted = (
            await session.execute(_DELETE_JOB_BATCH_SQL, {"days": days, "batch": batch})
        ).scalar_one()
        await session.commit()
        total += deleted
        if deleted < batch:
            break
        await asyncio.sleep(pause_s)
    logger.info("procrastinate_job_retention.done", deleted=total)
    return total


@procrastinate_app.periodic(cron="45 4 * * *")
@procrastinate_app.task(
    name="procrastinate_job_retention",
    queue="periodic",
    queueing_lock="procrastinate_job_retention_lock",
    priority=PERIODIC_MAINTENANCE_PRIORITY,
)
async def procrastinate_job_retention(timestamp: int) -> dict[str, int]:
    from app.db.session import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        return {"deleted": await sweep_succeeded_jobs(session)}
