"""In-process expiry sweep for unlisted runs (I-3.5, D-UP-17).

An asyncio loop, started from the FastAPI lifespan AFTER migrations + the pool
are up, that periodically deletes expired unlisted runs via the shared
`delete_run_cascade`. Race-safe across concurrent Machines via a session-level
`pg_advisory_lock` (a held lock makes the other Machine skip the tick, not block).
Coexists with the existing unreferenced-`artifact_blobs` sweep (distinct lock).

No Redis, no cron — the lazy generic-404 on expired tokens covers the gap if no
Machine is booted to run a tick.
"""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.session import AsyncSessionLocal
from app.models.scan_run import ScanRun
from app.scan.persistence import delete_run_cascade

logger = logging.getLogger(__name__)

# Distinct from the migration advisory lock (0x5AFE5C11).
_SWEEP_LOCK_KEY = 0x5AFE5C12


async def sweep_unlisted(session: AsyncSession) -> int:
    """Delete expired unlisted runs via `delete_run_cascade`. Returns rows swept.

    Guarded by `pg_try_advisory_lock(_SWEEP_LOCK_KEY)` — if another Machine holds
    it, this returns 0 immediately (no double-delete). Releases the lock before
    returning.
    """
    got = (
        await session.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": _SWEEP_LOCK_KEY})
    ).scalar_one()
    if not got:
        return 0
    try:
        ids = list(
            (
                await session.execute(
                    select(ScanRun.id).where(
                        ScanRun.visibility == "unlisted",
                        ScanRun.expires_at.is_not(None),
                        ScanRun.expires_at < func.now(),
                    )
                )
            )
            .scalars()
            .all()
        )
        for run_id in ids:
            await delete_run_cascade(session, run_id, allow_public=False)
        await session.commit()
        return len(ids)
    finally:
        await session.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": _SWEEP_LOCK_KEY})
        await session.commit()


async def sweep_ingestion_runs(session: AsyncSession, *, days: int = 90) -> int:
    """Delete `ingestion_runs` rows older than `days` (90-day retention). Returns
    rows swept. Guarded by the SAME advisory lock as `sweep_unlisted` so only one
    Machine sweeps per tick; releases it before returning.
    """
    got = (
        await session.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": _SWEEP_LOCK_KEY})
    ).scalar_one()
    if not got:
        return 0
    try:
        deleted = (
            await session.execute(
                text(
                    "WITH d AS (DELETE FROM ingestion_runs "
                    "WHERE started_at < now() - make_interval(days => :days) RETURNING 1) "
                    "SELECT count(*) FROM d"
                ),
                {"days": days},
            )
        ).scalar_one()
        await session.commit()
        return deleted
    finally:
        await session.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": _SWEEP_LOCK_KEY})
        await session.commit()


async def run_sweep_loop() -> None:
    """Every `settings.sweep_interval_seconds`, try the lock + sweep (unlisted runs
    + ingestion_runs retention). On error, log + continue (one bad tick never kills
    the task). Cancellation-safe."""
    interval = get_settings().sweep_interval_seconds
    logger.info("expiry sweep loop started (interval=%ss)", interval)
    try:
        while True:
            try:
                async with AsyncSessionLocal() as session:
                    swept = await sweep_unlisted(session)
                    swept_runs = await sweep_ingestion_runs(session)
                if swept or swept_runs:
                    logger.info(
                        "expiry sweep removed %d unlisted run(s), %d ingestion_run(s)",
                        swept,
                        swept_runs,
                    )
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("expiry sweep tick failed; continuing")
            await asyncio.sleep(interval)
    except asyncio.CancelledError:
        logger.info("expiry sweep loop cancelled")
        raise
