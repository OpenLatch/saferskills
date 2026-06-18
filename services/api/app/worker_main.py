"""Standalone Procrastinate worker entrypoint — `python -m app.worker_main`.

The deployed worker process (`services/worker/`) runs THIS, not uvicorn. It is
the same Docker image as the API with a different command, so the API process
(`app.main:app`) can be deployed with `INGESTION_WORKER_ENABLED=false` and stay
a lean web tier while the ingestion + bulk-scan queues drain here, sized
independently. Locally + in docker-compose the API still runs the worker
in-process (the default), so nothing about dev changes.

Boot mirrors the worker-relevant subset of `app.main`'s lifespan:

  observability → migrations (run_startup) → pool → boot reapers → connector +
  schema → supervisor → wait for SIGTERM/SIGINT → bounded teardown.

Deliberately NOT here (web-process-only): the expiry sweep loop (advisory lock
0x5AFE5C12 — stays in the API), FastAPI OTel instrumentation, routers, and the
interactive-scan background-task cleanup.
"""

from __future__ import annotations

import asyncio
import contextlib
import signal
import sys

import structlog

# Side-effect import: registers every ORM model against Base.metadata (so a job
# that touches a model has its table mapped), mirroring app.main.
import app.models  # noqa: F401  # pyright: ignore[reportUnusedImport]
from app.core.config import get_settings
from app.core.db_pool import close_pool, init_pool
from app.core.observability import init_observability, shutdown_observability
from app.core.shutdown import bounded, cancel_and_settle
from app.core.startup import run_startup
from app.core.startup_state import startup_state

logger = structlog.get_logger(__name__)


def _install_shutdown_signal(loop: asyncio.AbstractEventLoop) -> asyncio.Event:
    """A stop Event set on SIGTERM/SIGINT.

    `loop.add_signal_handler` is the clean asyncio path on POSIX (the deploy
    target). It raises `NotImplementedError` on Windows (local dev / tests) —
    there the returned Event simply never fires from a signal, which is fine
    because Windows isn't a deploy target for the worker and tests drive the
    boot sequence directly.
    """
    stop = asyncio.Event()
    with contextlib.suppress(NotImplementedError):
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, stop.set)
    return stop


async def main() -> int:
    """Run the worker until a shutdown signal, then tear down. Returns an exit code."""
    settings = get_settings()
    await init_observability(settings)

    # Migrations under the shared advisory lock (0x5AFE5C11) — race-safe vs the API
    # process running the same upgrade. run_startup self-handles failure (flips
    # startup_state); a worker with an unmigrated DB can do no useful work, so —
    # unlike the API, which serves /health in degraded mode — we exit non-zero and
    # let Fly's `[restart] policy` retry the boot.
    await run_startup()
    if not startup_state.is_healthy:
        logger.error("worker_main.startup_degraded", error=startup_state.migrations_error)
        return 1

    # Pool init is defensive — a job's DB work draws from the SQLAlchemy pool, but
    # any direct get_pool() path (SSE-style asyncpg) needs this too. Non-fatal.
    with contextlib.suppress(Exception):
        await init_pool()

    # Boot reapers — idempotent, safe to run in BOTH processes (advisory-scoped /
    # rowcount-bounded). They flip orphaned `running` rows a prior crash left behind.
    with contextlib.suppress(Exception):
        from app.queue.scan_runner import recover_stale_scans

        await recover_stale_scans()
    with contextlib.suppress(Exception):
        from app.ingestion.tasks import recover_stale_ingestion_runs

        await recover_stale_ingestion_runs()

    from app.ingestion import procrastinate_app
    from app.ingestion.worker import (
        apply_procrastinate_schema_locked,
        assert_worker_concurrency_budget,
        ingestion_worker_supervisor,
    )

    # Fail fast on a misconfigured concurrency-vs-pool budget (a deploy error).
    assert_worker_concurrency_budget()
    await procrastinate_app.open_async()
    await apply_procrastinate_schema_locked()

    # Boot-time orphan recovery — the previous worker is gone, so any `doing`
    # Procrastinate job is an orphan whose `queueing_lock` blocks fresh cycles.
    # Re-queue them NOW (the periodic retriers' 4h grace is too slow after a deploy
    # restart — that delay is what stalled staging ingestion post-redeploy). Runs
    # after the connector opens (job_manager needs it) + before the supervisor.
    with contextlib.suppress(Exception):
        from app.ingestion.tasks_scan import recover_orphaned_jobs_at_boot

        recovered = await recover_orphaned_jobs_at_boot()
        logger.info("worker_main.orphan_recovery", **recovered)

    loop = asyncio.get_running_loop()
    stop = _install_shutdown_signal(loop)
    worker_task = asyncio.create_task(
        ingestion_worker_supervisor(), name="ingestion_worker_supervisor"
    )
    logger.info("worker_main.started", concurrency=settings.ingestion_worker_concurrency)

    # Run until a signal — OR until the supervisor itself returns (it only does so
    # on a fatal error; the restart-on-self-stop loop keeps it alive otherwise).
    stop_task = asyncio.create_task(stop.wait(), name="worker_stop_signal")
    try:
        await asyncio.wait({worker_task, stop_task}, return_when=asyncio.FIRST_COMPLETED)
    finally:
        if not stop_task.done():
            stop_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await stop_task

    logger.info("worker_main.shutting_down")
    # Bounded teardown — same helpers + order as app.main's lifespan finally.
    await cancel_and_settle(
        worker_task,
        timeout=settings.ingestion_worker_shutdown_timeout_s + 2.0,
        label="ingestion worker",
    )
    await bounded(procrastinate_app.close_async(), timeout=5.0, label="procrastinate close")
    await bounded(asyncio.to_thread(shutdown_observability), timeout=5.0, label="posthog flush")
    await bounded(close_pool(), timeout=5.0, label="db pool close")
    return 0


if __name__ == "__main__":  # pragma: no cover — process entrypoint
    sys.exit(asyncio.run(main()))
