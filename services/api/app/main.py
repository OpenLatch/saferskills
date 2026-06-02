"""FastAPI entrypoint for the SaferSkills API.

W1 surface: /api/v1/health only. The scan engine, ingestion adapters, and
catalog/report endpoints land via Initiatives I-02 / I-03 / I-04 starting W2.
"""

import asyncio
import contextlib
import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Side-effect import: registers every ORM model against Base.metadata.
import app.models  # pyright: ignore[reportUnusedImport]
from app.core.config import get_settings
from app.core.db_pool import close_pool, init_pool
from app.core.middleware import StartupGuardMiddleware
from app.core.observability import init_observability
from app.core.startup import run_startup
from app.core.startup_state import startup_state
from app.routers import health, items, scans, stats, vendor

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

    try:
        yield
    finally:
        if sweep_task is not None:
            sweep_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await sweep_task
        await close_pool()


app = FastAPI(
    title="SaferSkills API",
    description=(
        "Every AI skill, independently scanned — public, free, Apache-2.0 "
        "trust-scoring for skills, MCP servers, hooks, and plugins."
    ),
    version="0.0.0+foundation",
    lifespan=lifespan,
    openapi_url="/openapi.json",
    docs_url="/docs",
    redoc_url=None,
)

# Degraded-mode guard — registered BEFORE CORS so CORS stays the outermost
# layer and OPTIONS preflight still succeeds even when the API is degraded.
app.add_middleware(StartupGuardMiddleware)

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
