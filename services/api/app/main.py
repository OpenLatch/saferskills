"""FastAPI entrypoint for the SaferSkills API.

Serves the health check, the scan engine, the ingestion adapters, and the
catalog/report endpoints.
"""

import asyncio
import contextlib
import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DBAPIError
from sqlalchemy.exc import TimeoutError as SQLAlchemyTimeoutError

# Side-effect import: registers every ORM model against Base.metadata.
import app.models  # pyright: ignore[reportUnusedImport]
from app.core.access_log_middleware import AccessLogMiddleware
from app.core.config import get_settings
from app.core.db_pool import close_pool, init_pool
from app.core.middleware import StartupGuardMiddleware, service_unavailable_response
from app.core.observability import (
    init_observability,
    instrument_app,
    record_pool_timeout_breadcrumb,
    record_statement_timeout_breadcrumb,
    shutdown_observability,
)
from app.core.startup import run_startup
from app.core.startup_state import startup_state
from app.routers import (
    admin,
    agent_scans,
    community,
    health,
    installs,
    items,
    scans,
    sitemap,
    stats,
    vendor,
    webhooks,
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None]:
    settings = get_settings()
    await init_observability(settings)
    # OTel auto-instrumentation (FastAPI/SQLAlchemy/HTTPX) — only once the
    # TracerProvider is configured (endpoint set). Non-fatal: a broken
    # instrumentor must never keep the app from booting.
    if settings.otel_exporter_otlp_endpoint:
        with contextlib.suppress(Exception):
            instrument_app(_app)
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
    # Same idea for orphaned `running` ingestion_runs rows (a reload between
    # record_run_started/finished) — the missing ingest-side reaper. Clears the
    # phantom `stuck`/inflated-`running` the eagle-eye view would otherwise show.
    with contextlib.suppress(Exception):
        from app.ingestion.tasks import recover_stale_ingestion_runs

        await recover_stale_ingestion_runs()

    # Unlisted-run expiry sweep — only once migrations + pool are up, never in
    # degraded mode. Cancelled cleanly on shutdown.
    sweep_task: asyncio.Task[None] | None = None
    if startup_state.is_healthy:
        from app.core.sweeps import run_sweep_loop

        sweep_task = asyncio.create_task(run_sweep_loop())

    # Slack-invite health probe — same healthy-only guard as the sweep, plus a
    # configured invite URL (nothing to probe otherwise). Alerts on a broken
    # never-expire community-Slack link; cancelled cleanly on shutdown.
    health_task: asyncio.Task[None] | None = None
    if startup_state.is_healthy and settings.slack_invite_url:
        from app.services.slack_invite_health import run_slack_invite_health_loop

        health_task = asyncio.create_task(run_slack_invite_health_loop())

    # Procrastinate connector + (optionally) the in-process worker.
    # After migrations + pool init — mirrors the sweep guard above. Schema applied
    # idempotently under a FRESH advisory lock 0x5AFE5C13.
    ingestion_task: asyncio.Task[None] | None = None
    if startup_state.is_healthy:
        if settings.ingestion_worker_enabled:
            from app.ingestion.worker import assert_worker_concurrency_budget

            # Static-config invariant — fail fast (refuse to boot) on a misconfigured
            # concurrency-vs-pool budget, BEFORE opening anything. A deploy error,
            # not the transient DB-unreachable class the degraded-mode path handles.
            # Only the worker process cares about it.
            assert_worker_concurrency_budget()

        # Open the connector + apply its schema REGARDLESS of whether THIS process
        # runs the worker. The API's own defer paths — webhook dispatch
        # (`routers/webhooks.py`), admin force-cycle + popularity recompute
        # (`routers/admin.py`) — call `procrastinate_app.defer_async`, which needs the
        # connector open + the schema present. With the worker split to its own
        # process (`INGESTION_WORKER_ENABLED=false` on the API) this branch is the
        # ONLY thing keeping those endpoints from 500ing. Idempotent + advisory-locked
        # → running it here AND in the worker process is safe. NOT contextlib.suppress:
        # log the full traceback + flag degraded (surfaced on /api/v1/health)
        # so a failed connector is visible, but do NOT re-raise (a transient DB-at-boot
        # must not crash the API).
        try:
            from app.ingestion import procrastinate_app
            from app.ingestion.worker import apply_procrastinate_schema_locked

            await procrastinate_app.open_async()
            await apply_procrastinate_schema_locked()
        except Exception as exc:
            logger.error("procrastinate connector failed to open", exc_info=True)
            startup_state.mark_ingestion_degraded(str(exc))
        else:
            if settings.ingestion_worker_enabled:
                from app.ingestion.worker import ingestion_worker_supervisor

                ingestion_task = asyncio.create_task(
                    ingestion_worker_supervisor(), name="ingestion_worker_supervisor"
                )

    try:
        yield
    finally:
        # Every teardown step is BOUNDED — the lifespan `finally` must return in a
        # few seconds no matter what a background task or close coroutine does, or
        # uvicorn's "Waiting for application shutdown." hangs forever (the symptom
        # that motivated this: a `--reload` mid-ingestion never reloaded). Order:
        # connection-holders first (so they release sessions), pools last.
        from app.core.shutdown import bounded, cancel_and_settle

        # 1. Interactive fire-and-forget scan tasks (routers/scans.py) — orphaned
        #    otherwise, running on into a dying loop.
        with contextlib.suppress(Exception):
            await scans.cancel_background_scans(timeout=5.0)
        # 2. Ingestion worker — the primary hang source. Its own
        #    `shutdown_graceful_timeout` aborts in-flight jobs; allow a little
        #    slack over that before we abandon the supervisor task itself.
        await cancel_and_settle(
            ingestion_task,
            timeout=settings.ingestion_worker_shutdown_timeout_s + 2.0,
            label="ingestion worker",
        )
        with contextlib.suppress(Exception):
            from app.ingestion import procrastinate_app

            await bounded(procrastinate_app.close_async(), timeout=5.0, label="procrastinate close")
        # 3. Expiry sweep loop.
        await cancel_and_settle(sweep_task, timeout=5.0, label="expiry sweep")
        # 3b. Slack-invite health probe loop.
        await cancel_and_settle(health_task, timeout=5.0, label="slack invite health")
        # 4. PostHog — flush buffered events before the loop closes (bounded; the
        #    sync client.shutdown() runs in a thread so it can't hang teardown).
        await bounded(asyncio.to_thread(shutdown_observability), timeout=5.0, label="posthog flush")
        # 5. SQLAlchemy pool — last, after every session-holder is gone.
        await bounded(close_pool(), timeout=5.0, label="db pool close")


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
    """Map a SQLAlchemy pool-checkout timeout to a bounded 503.

    Under contention the shared pool's `pool_timeout` raises after
    `db_pool_timeout_s` instead of every request hanging until the ingestion
    worker frees a slot. A bounded, observable failure beats a silent hang.
    """
    record_pool_timeout_breadcrumb("api")
    return service_unavailable_response("Database connection pool exhausted — retry shortly.")


# Postgres cancellation SQLSTATEs that mean "the DB is under pressure" — map to a
# bounded 503, not a 500. 57014 = query_canceled (statement_timeout fired); 25P03
# = idle_in_transaction_session_timeout. Both free the connection cleanly.
_DB_PRESSURE_SQLSTATES = frozenset({"57014", "25P03"})


def _db_pressure_sqlstate(exc: DBAPIError) -> str | None:
    """Return the Postgres SQLSTATE of a DB-pressure cancellation, else None.

    `statement_timeout` surfaces as a SQLAlchemy `DBAPIError` (the base, not
    `OperationalError`) whose `.orig` is the asyncpg-dialect wrapper (NOT the raw
    asyncpg `QueryCanceledError`); the wrapper's `sqlstate` attribute is the
    reliable signal (verified against the live asyncpg dialect). Falls back to
    `pgcode` for resilience across dialect versions.
    """
    orig = getattr(exc, "orig", None)
    sqlstate = getattr(orig, "sqlstate", None) or getattr(orig, "pgcode", None)
    return sqlstate if sqlstate in _DB_PRESSURE_SQLSTATES else None


@app.exception_handler(DBAPIError)
async def _statement_timeout_handler(  # pyright: ignore[reportUnusedFunction]
    _request: Request, exc: DBAPIError
) -> JSONResponse:
    """Map a Postgres statement-timeout cancellation to a bounded 503.

    Sibling to `_pool_timeout_handler`: where that bounds a *checkout* wait, this
    bounds a *query* — `statement_timeout` (set in `db/session.py` connect_args)
    aborts a slow query so it can't pin a pooled connection indefinitely while
    every other request 503s at the pool-checkout timeout. A non-pressure
    `DBAPIError` (a genuine DB/driver error, e.g. an uncaught constraint
    violation) is re-raised so it still becomes a 500 + Sentry capture, exactly
    as before this handler existed.
    """
    if _db_pressure_sqlstate(exc) is not None:
        record_statement_timeout_breadcrumb("api")
        return service_unavailable_response(
            "Database is under load — the query exceeded the statement timeout; retry shortly."
        )
    raise exc


# Degraded-mode guard — registered BEFORE CORS so CORS stays the outermost
# layer and OPTIONS preflight still succeeds even when the API is degraded.
app.add_middleware(StartupGuardMiddleware)

# Access-log writer — inner to CORS so it only sees requests that passed
# the CORS gate; write-only B2B-funnel signal with redacted IPs (privacy.md).
app.add_middleware(AccessLogMiddleware)

# CORS posture: origins from `settings.cors_allowed_origins` (env-driven).
# Tightens to auth + per-route when auth lands.
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
# Agent Scan — run-lifecycle + token-gated signed pack + flat pubkey map.
app.include_router(agent_scans.router, prefix="/api/v1")
app.include_router(agent_scans.pack_keys_router, prefix="/api/v1")
app.include_router(items.router, prefix="/api/v1")
# Sitemap — DB-backed crawl-discovery index + shards (webapp relays at the apex).
app.include_router(sitemap.router, prefix="/api/v1")
app.include_router(stats.router, prefix="/api/v1")
app.include_router(vendor.router, prefix="/api/v1")
# Install CLI support — opt-in install telemetry. (Finding prose is inlined
# server-side onto each report finding, not served from a corpus endpoint.)
app.include_router(installs.router, prefix="/api/v1")
# Admin surface — X-Admin-Key gated; /api/v1/admin/*.
app.include_router(admin.router, prefix="/api/v1")
# Community — stable /slack redirect hop to the shared community Slack invite.
app.include_router(community.router, prefix="/api/v1")
# Webhook intake — note: NO /api/v1 prefix; GitHub posts to /webhooks/github.
app.include_router(webhooks.router)
