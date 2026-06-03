"""Procrastinate worker lifecycle — started in the FastAPI lifespan (D-04-03).

In-process, same Machine, same Postgres. Schema applied idempotently at startup
under a FRESH advisory lock 0x5AFE5C13 (0x…11 = migrations, 0x…12 = expiry sweep
are taken), mirroring run_startup() + run_sweep_loop(). Never an Alembic migration.
"""

from __future__ import annotations

import asyncio

import structlog
from sqlalchemy import text

from app.core.config import get_settings
from app.db.session import AsyncSessionLocal
from app.ingestion import ALL_QUEUES, procrastinate_app

logger = structlog.get_logger(__name__)

_INGESTION_LOCK_KEY = 0x5AFE5C13


async def apply_procrastinate_schema_locked() -> None:
    """Apply the procrastinate_* schema idempotently, serialised by an advisory lock.

    The app must already be opened (`procrastinate_app.open_async()`) by the caller.

    Procrastinate's ``apply_schema_async()`` emits raw ``CREATE TYPE`` / ``CREATE TABLE``
    (no ``IF NOT EXISTS``), so it is a once-only operation: re-running it on a Postgres
    that already has the schema raises ``type "procrastinate_job_status" already exists``.
    We therefore guard on the presence of ``procrastinate_jobs`` inside the lock and only
    apply when it is absent — making boot-time apply safe on every restart. The advisory
    lock keeps concurrent Machines race-free (first applies, the rest see the table + skip).
    """
    async with AsyncSessionLocal() as lock_session:
        await lock_session.execute(text("SELECT pg_advisory_lock(:k)"), {"k": _INGESTION_LOCK_KEY})
        try:
            already_applied = (
                await lock_session.execute(text("SELECT to_regclass('procrastinate_jobs')"))
            ).scalar() is not None
            if already_applied:
                logger.info("procrastinate.schema_already_applied")
            else:
                await procrastinate_app.schema_manager.apply_schema_async()
                logger.info("procrastinate.schema_applied")
        finally:
            await lock_session.execute(
                text("SELECT pg_advisory_unlock(:k)"), {"k": _INGESTION_LOCK_KEY}
            )
            await lock_session.commit()


async def ingestion_worker_supervisor() -> None:
    """Run the worker with an auto-restart backoff loop. Cancellation propagates."""
    settings = get_settings()
    backoff_s = 5.0
    while True:
        try:
            await procrastinate_app.run_worker_async(
                queues=ALL_QUEUES,
                concurrency=settings.ingestion_worker_concurrency,
                install_signal_handlers=False,  # FastAPI owns the signal handlers
            )
            return  # graceful shutdown
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("ingestion.worker_crashed_restarting", backoff_s=backoff_s)
            await asyncio.sleep(backoff_s)
            backoff_s = min(backoff_s * 2, 60.0)
