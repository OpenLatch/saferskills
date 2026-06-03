"""FastAPI entrypoint for the SaferSkills API.

W1 surface: /api/v1/health only. The scan engine, ingestion adapters, and
catalog/report endpoints land via Initiatives I-02 / I-03 / I-04 starting W2.
"""

import asyncio
import contextlib
import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import TimeoutError as SQLAlchemyTimeoutError

# Side-effect import: registers every ORM model against Base.metadata.
import app.models  # pyright: ignore[reportUnusedImport]
from app.core.access_log_middleware import AccessLogMiddleware
from app.core.config import get_settings
from app.core.db_pool import close_pool, init_pool
from app.core.middleware import StartupGuardMiddleware, service_unavailable_response
from app.core.observability import init_observability, record_pool_timeout_breadcrumb
from app.core.startup import run_startup
from app.core.startup_state import startup_state
from app.routers import admin, health, items, scans, stats, vendor, webhooks

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None]:
    settings = get_settings()
    await init_observability(settings)
    # Bring the DB to head before anything touches it. `run_startup()` is NOT
    # suppressed — it self-handles failure by entering degraded mode (the
    # StartupGuardMiddleware then serves 503 on every route but /health).
    await run_startup()
    # Pool init failures are non-fatal at boot — health endpoint still serves;
    # any route that needs the pool will raise on its own. Same for the
    # stale-scan recovery sweep: missing DB at boot shouldn't keep /health red.
    with contextlib.suppress(Exception):
        await init_pool()
    with contextlib.suppress(Exception):
        from app.queue.scan_runner import recover_stale_scans

        await recover_stale_scans()

    # Unlisted-run expiry sweep — only once migrations + pool are up, never in
    # degraded mode (I-3.5, D-UP-17 / P1-7). Cancelled cleanly on shutdown.
    sweep_task: asyncio.Task[None] | None = None
    if startup_state.is_healthy:
        from app.core.sweeps import run_sweep_loop

        sweep_task = asyncio.create_task(run_sweep_loop())

    # In-process Procrastinate ingestion worker (I-04 D-04-03). Only when healthy
    # and enabled, after migrations + pool init — mirrors the sweep guard above.
    # Schema applied idempotently under a FRESH advisory lock 0x5AFE5C13.
    ingestion_task: asyncio.Task[None] | None = None
    if startup_state.is_healthy and settings.ingestion_worker_enabled:
        from app.ingestion.worker import assert_worker_concurrency_budget

        # Static-config invariant — fail fast (refuse to boot) on a misconfigured
        # concurrency-vs-pool budget, BEFORE the suppress below (crash-resilience
        # §1.5). This is a deploy error, not the transient DB-unreachable class
        # the degraded-mode path handles.
        assert_worker_concurrency_budget()
        with contextlib.suppress(Exception):
            from app.ingestion import procrastinate_app
            from app.ingestion.worker import (
                apply_procrastinate_schema_locked,
                ingestion_worker_supervisor,
            )

            await procrastinate_app.open_async()
            await apply_procrastinate_schema_locked()
            ingestion_task = asyncio.create_task(
                ingestion_worker_supervisor(), name="ingestion_worker_supervisor"
            )

    try:
        yield
    finally:
        if ingestion_task is not None:
            ingestion_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await ingestion_task
            with contextlib.suppress(Exception):
                from app.ingestion import procrastinate_app

                await procrastinate_app.close_async()
        if sweep_task is not None:
            sweep_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await sweep_task
        await close_pool()


app = FastAPI(
    title="SaferSkills API",
    description=(
        "Every AI capability, independently scanned — public, free, Apache-2.0 "
        "trust-scoring for skills, MCP servers, hooks, and plugins."
    ),
    version="0.0.0+foundation",
    lifespan=lifespan,
    openapi_url="/openapi.json",
    docs_url="/docs",
    redoc_url=None,
)


@app.exception_handler(SQLAlchemyTimeoutError)
async def _pool_timeout_handler(  # pyright: ignore[reportUnusedFunction]
    _request: Request, _exc: SQLAlchemyTimeoutError
) -> JSONResponse:
    """Map a SQLAlchemy pool-checkout timeout to a bounded 503 (crash-resilience §1.3).

    Under contention the shared pool's `pool_timeout` raises after
    `db_pool_timeout_s` instead of every request hanging until the ingestion
    worker frees a slot. A bounded, observable failure beats a silent hang.
    """
    record_pool_timeout_breadcrumb("api")
    return service_unavailable_response("Database connection pool exhausted — retry shortly.")


# Degraded-mode guard — registered BEFORE CORS so CORS stays the outermost
# layer and OPTIONS preflight still succeeds even when the API is degraded.
app.add_middleware(StartupGuardMiddleware)

# Access-log writer (I-04) — inner to CORS so it only sees requests that passed
# the CORS gate; write-only B2B-funnel signal with redacted IPs (privacy.md).
app.add_middleware(AccessLogMiddleware)

# CORS posture: origins from `settings.cors_allowed_origins` (env-driven).
# Tightens to auth + per-route in Track E.
_settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=_settings.cors_allowed_origins,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    allow_credentials=False,
)

app.include_router(health.router, prefix="/api/v1")
app.include_router(scans.router, prefix="/api/v1")
app.include_router(items.router, prefix="/api/v1")
app.include_router(stats.router, prefix="/api/v1")
app.include_router(vendor.router, prefix="/api/v1")
# Admin surface (I-04 Phase C) — X-Admin-Key gated; /api/v1/admin/*.
app.include_router(admin.router, prefix="/api/v1")
# Webhook intake (I-04) — note: NO /api/v1 prefix; GitHub posts to /webhooks/github.
app.include_router(webhooks.router)
