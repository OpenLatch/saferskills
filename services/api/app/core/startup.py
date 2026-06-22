"""Startup orchestration — runs `alembic upgrade head` on every API boot.

Startup sequence (runs on every Machine boot, in every environment):
  1. Migrations — `alembic upgrade head`, guarded by a pg advisory lock so
                  multiple Machines booting concurrently don't race the DDL.
  2. Ready      — API begins accepting traffic.

The sequence retries up to 5 times with exponential backoff (2s, 4s, 8s, 16s)
when the database is unreachable, then enters degraded mode (503 on all
endpoints except /api/v1/health) if all attempts fail. `run_startup()` never
re-raises — degraded mode is the failure contract.

Ported faithfully from openlatch-platform's migration subsystem, trimmed to
migrations only: SaferSkills is single-tenant + auth-less + role-less, so the
platform's bootstrap_db / seed / partition / RLS-grant stages don't exist here.

Usage:
    from app.core.startup import run_startup
    await run_startup()
"""

import asyncio

import structlog
from sqlalchemy import text

from app.core.config import get_settings
from app.core.startup_state import startup_state
from app.db.session import AsyncSessionLocal, async_engine

logger = structlog.get_logger(__name__)

STARTUP_MAX_RETRIES = 5
STARTUP_BASE_DELAY_SECONDS = 2

# Arbitrary but constant 32-bit int for the cluster-wide migration mutex.
# pg_advisory_lock is keyed on this — any Machine holding this lock blocks all
# other Machines trying to run migrations until it releases.
_MIGRATION_LOCK_KEY = 0x5AFE5C11


def _run_migrations_sync() -> None:
    """Run `alembic upgrade head` synchronously.

    Intended to be called via run_in_executor() so that alembic env.py's
    internal `asyncio.run()` (migrations/env.py:83) does not collide with the
    running event loop (`asyncio.run() cannot be called from a running event
    loop`). Relies on cwd being `services/api` / `/app` so `script_location =
    migrations` + `prepend_sys_path = .` in alembic.ini resolve.
    """
    from alembic import command
    from alembic.config import Config

    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", get_settings().database_url)
    command.upgrade(cfg, "head")


async def _run_migrations_locked() -> None:
    """Run `alembic upgrade head` under a pg advisory lock.

    Multiple API Machines boot simultaneously on deploy. Without a mutex they'd
    all call `alembic upgrade head` concurrently — the first would succeed,
    others would race or fail on duplicate DDL. The lock is held on this
    session's own connection via `pg_advisory_lock(key)`; subsequent Machines
    block there until we release, at which point alembic sees `head` and the
    upgrade is a no-op. The actual migration runs on env.py's separate fresh
    async engine — correct for session-level locks.
    """
    log = logger.bind(step="migrations", lock_key=_MIGRATION_LOCK_KEY)

    async with AsyncSessionLocal() as lock_session:
        # This session HOLDS the migration advisory lock for the whole migration
        # (which runs on env.py's separate engine), sitting idle-in-transaction
        # meanwhile. The shared engine's statement_timeout +
        # idle_in_transaction_session_timeout (db/session.py connect_args) must NOT
        # apply here: the timeout would abort the blocking `pg_advisory_lock` wait
        # under multi-Machine contention, and idle_in_transaction would TERMINATE
        # this session mid-migration — releasing the session-level lock and letting
        # another Machine race the DDL. `SET LOCAL` scopes the exemption to this
        # one transaction (no pooled-connection contamination).
        await lock_session.execute(text("SET LOCAL statement_timeout = 0"))
        await lock_session.execute(text("SET LOCAL idle_in_transaction_session_timeout = 0"))
        await lock_session.execute(
            text("SELECT pg_advisory_lock(:key)"), {"key": _MIGRATION_LOCK_KEY}
        )
        log.info("migrations_lock_acquired")
        try:
            log.info("migrations_start")
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, _run_migrations_sync)
            log.info("migrations_complete")
        finally:
            await lock_session.execute(
                text("SELECT pg_advisory_unlock(:key)"), {"key": _MIGRATION_LOCK_KEY}
            )
            log.info("migrations_lock_released")


async def run_startup() -> None:
    """Run migrations with retries; enter degraded mode on exhaustion.

    Retries up to 5 times with exponential backoff (2s, 4s, 8s, 16s) when the
    database is unreachable. Never re-raises — on success marks the startup
    state healthy and disposes the runtime engine (refreshes asyncpg's codec
    caches after the DDL); on exhaustion marks the state degraded so the
    StartupGuardMiddleware serves 503.
    """
    log = logger.bind(component="startup")
    log.info("startup_begin")

    last_error: Exception | None = None

    for attempt in range(1, STARTUP_MAX_RETRIES + 1):
        try:
            await _run_migrations_locked()
            startup_state.mark_migrations_ok()
            # Refresh asyncpg's per-connection type codec caches post-DDL: new
            # columns/types added by the migration must be seen by the runtime
            # pool's connections, which may have been established pre-upgrade.
            await async_engine.dispose()
            log.info("startup_complete", status="ready", attempt=attempt)
            return
        except Exception as exc:  # degraded mode is the failure contract
            last_error = exc
            if attempt < STARTUP_MAX_RETRIES:
                delay = STARTUP_BASE_DELAY_SECONDS * (2 ** (attempt - 1))
                log.warning(
                    "startup_retry",
                    attempt=attempt,
                    max_retries=STARTUP_MAX_RETRIES,
                    next_retry_seconds=delay,
                    error=str(exc),
                )
                await asyncio.sleep(delay)
            else:
                log.error(
                    "startup_failed",
                    attempts=STARTUP_MAX_RETRIES,
                    error=str(exc),
                )

    # All retries exhausted — mark degraded (never re-raise).
    startup_state.mark_migrations_failed(str(last_error))
