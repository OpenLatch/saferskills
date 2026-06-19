"""Procrastinate worker lifecycle — started in the FastAPI lifespan.

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


def worker_concurrency() -> int:
    """Total worker slots = ingestion concurrency + the durable scan-job budget.

    The single in-process worker drains both the ingest queues and the `scan`
    queue; scan jobs are separately capped at SCAN_MAX_CONCURRENCY by an in-body
    semaphore (tasks_scan), so handing the worker the sum lets ingestion keep its
    configured slots while scan work runs alongside up to its own cap."""
    settings = get_settings()
    return settings.ingestion_worker_concurrency + settings.scan_max_concurrency


def assert_worker_concurrency_budget() -> None:
    """Refuse a config that lets the worker drain the API's SQLAlchemy pool.

    Ingestion + scan tasks draw their sessions from the SAME SQLAlchemy pool the
    public API serves from, so the combined worker concurrency must leave
    comfortable headroom for API traffic.
    Asserted against `db_pool_size + db_max_overflow` (the worker may legitimately
    consume overflow under load; the headroom default — 4 + 4 = 8 vs 15 — keeps
    it well clear).

    Called both synchronously at lifespan startup (so a misconfigured deploy
    refuses to boot rather than silently mis-size a background task) and at the
    top of the supervisor (so a direct call validates too).
    """
    settings = get_settings()
    if worker_concurrency() >= settings.db_pool_size + settings.db_max_overflow:
        raise RuntimeError(
            "ingestion_worker_concurrency + scan_max_concurrency must leave "
            "SQLAlchemy headroom for the API; got "
            f"ingestion={settings.ingestion_worker_concurrency} + "
            f"scan={settings.scan_max_concurrency} vs "
            f"pool={settings.db_pool_size}+{settings.db_max_overflow}"
        )


async def ingestion_worker_supervisor() -> None:
    """Run the worker, restarting it on any unexpected stop. ONLY cancellation exits.

    The only intended exit is the FastAPI lifespan cancelling this task on shutdown,
    which surfaces as ``CancelledError`` (re-raised below). Every other outcome means
    the worker stopped when it shouldn't have, and we restart it with backoff:

    - **A normal return is NOT a graceful shutdown.** Procrastinate self-stops the
      worker — ``run_worker_async`` returns *normally*, it does not raise — when a
      side task (notably the DB heartbeat) fails on a transient connection drop, e.g.
      a Postgres machine restart or a Fly-proxy connection recycle (see
      ``procrastinate/worker.py::_monitor_side_tasks``). We run with
      ``install_signal_handlers=False`` and ``wait=True``, so there is no other path
      to a clean return. Treating it as graceful shutdown (the old ``return``) left a
      routine PG blip permanently killing ingestion AND the bulk-scan queue — and
      because the reaper / scheduler / alert-evaluator are themselves Procrastinate
      tasks, every safety net died with the worker, invisibly to Fly's HTTP-only
      health check. So a return restarts, it never exits.
    - **An exception** (a real crash) restarts the same way.
    """
    assert_worker_concurrency_budget()
    backoff_s = 5.0
    while True:
        try:
            await procrastinate_app.run_worker_async(
                queues=ALL_QUEUES,
                concurrency=worker_concurrency(),
                install_signal_handlers=False,  # FastAPI owns the signal handlers
                # Bound the graceful-shutdown wait so a `--reload` mid-cycle can't
                # hang forever on an in-flight job — _shutdown waits at most this
                # long then ABORTS running jobs (Procrastinate re-queues them).
                shutdown_graceful_timeout=get_settings().ingestion_worker_shutdown_timeout_s,
            )
            # Reached only when Procrastinate self-stopped (side-task failure) — an
            # unexpected stop, not a shutdown. Restart with backoff.
            logger.warning("ingestion.worker_self_stopped_restarting", backoff_s=backoff_s)
        except asyncio.CancelledError:
            raise  # lifespan teardown — the one intended exit
        except Exception:
            logger.exception("ingestion.worker_crashed_restarting", backoff_s=backoff_s)
        await asyncio.sleep(backoff_s)
        backoff_s = min(backoff_s * 2, 60.0)
