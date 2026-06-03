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
    """
    async with AsyncSessionLocal() as lock_session:
        await lock_session.execute(text("SELECT pg_advisory_lock(:k)"), {"k": _INGESTION_LOCK_KEY})
        try:
            await procrastinate_app.schema_manager.apply_schema_async()
            logger.info("procrastinate.schema_applied")
        finally:
            await lock_session.execute(
                text("SELECT pg_advisory_unlock(:k)"), {"k": _INGESTION_LOCK_KEY}
            )
            await lock_session.commit()


def assert_worker_concurrency_budget() -> None:
    """Refuse a config that lets the worker drain the API's SQLAlchemy pool.

    Ingestion tasks draw their sessions from the SAME SQLAlchemy pool the public
    API serves from, so the worker concurrency must leave comfortable headroom
    for API traffic (crash-resilience addendum §1.5). Asserted against
    `db_pool_size + db_max_overflow` (the worker may legitimately consume
    overflow under load; the headroom default — 4 vs 15 — keeps it well clear).

    Called both synchronously at lifespan startup (so a misconfigured deploy
    refuses to boot rather than silently mis-size a background task) and at the
    top of the supervisor (so a direct call validates too).
    """
    settings = get_settings()
    if settings.ingestion_worker_concurrency >= settings.db_pool_size + settings.db_max_overflow:
        raise RuntimeError(
            "ingestion_worker_concurrency must leave SQLAlchemy headroom for the API; "
            f"got concurrency={settings.ingestion_worker_concurrency} vs "
            f"pool={settings.db_pool_size}+{settings.db_max_overflow}"
        )


async def ingestion_worker_supervisor() -> None:
    """Run the worker with an auto-restart backoff loop. Cancellation propagates."""
    settings = get_settings()
    assert_worker_concurrency_budget()
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
