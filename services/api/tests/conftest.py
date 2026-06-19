"""Pytest fixtures for the SaferSkills API test suite.

Provides:
- `db_engine`: a session-scoped async engine bound to DATABASE_URL_TEST (falls
  back to the dev DSN with a `_test` suffix). The migration head is applied
  once per session.
- `db_session`: a per-test AsyncSession wrapped in a SAVEPOINT-style nested
  transaction that rolls back at teardown — keeps tests isolated without
  re-running the migration each time.
- `client`: an httpx.AsyncClient against the in-process FastAPI app.

The DB fixtures are opt-in: tests that don't need them simply don't import
them. The smoke test for /api/v1/health stays free of DB dependencies so the
no-postgres case (CI lane defaulting to test_health-only) still passes.
"""

from __future__ import annotations

import asyncio
import os
import sys
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.main import app


@pytest.fixture(autouse=True)
def _migrations_ok() -> Iterator[None]:  # pyright: ignore[reportUnusedFunction]
    """Default every test to the healthy startup state.

    The lifespan (which runs `run_startup()` → `mark_migrations_ok()`) never
    fires under httpx's `ASGITransport`, so without this the singleton stays at
    its `migrations_ok=False` default and `StartupGuardMiddleware` would 503
    every non-`/health` route. Tests that exercise degraded mode toggle the
    state themselves; this fixture saves/restores around each test.
    """
    from app.core.startup_state import startup_state

    prev_ok = startup_state.migrations_ok
    prev_err = startup_state.migrations_error
    startup_state.mark_migrations_ok()
    try:
        yield
    finally:
        startup_state.migrations_ok = prev_ok
        startup_state.migrations_error = prev_err


# Resolve the project root (services/api/) so the alembic.ini path is stable
# regardless of where pytest is invoked from.
_API_ROOT = Path(__file__).resolve().parent.parent
_ALEMBIC_INI = _API_ROOT / "alembic.ini"


def _test_database_url() -> str:
    """Pick the DB URL for tests.

    Honour DATABASE_URL_TEST if set (CI lane will point this at a dedicated
    test DB); otherwise mutate the dev DSN by appending `_test` to the
    database name. Keeps the dev DB safe from test-side data churn.
    """
    explicit = os.environ.get("DATABASE_URL_TEST")
    if explicit:
        return explicit
    dev = os.environ.get(
        "DATABASE_URL",
        "postgresql+asyncpg://postgres:dev@localhost:5432/saferskills_dev",
    )
    if dev.endswith("_test"):
        return dev
    return f"{dev}_test"


@pytest_asyncio.fixture(scope="session")
async def db_engine() -> AsyncIterator[object]:
    """Session-scoped async engine. Runs `alembic upgrade head` once.

    Migrations run in a subprocess so alembic gets its own event loop —
    calling `alembic.command.upgrade()` directly from inside a pytest-asyncio
    fixture collides with the running loop (`asyncio.run() cannot be called
    from a running event loop`).
    """
    url = _test_database_url()
    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "alembic",
        "upgrade",
        "head",
        cwd=_API_ROOT,
        env={**os.environ, "DATABASE_URL": url},
    )
    returncode = await proc.wait()
    if returncode != 0:
        raise RuntimeError(f"alembic upgrade head failed with exit code {returncode}")

    engine = create_async_engine(url, pool_pre_ping=True)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_engine: object) -> AsyncIterator[AsyncSession]:
    """Per-test session inside a SAVEPOINT — auto-rollback at teardown."""
    factory = async_sessionmaker(bind=db_engine, expire_on_commit=False, class_=AsyncSession)  # type: ignore[arg-type]
    async with factory() as session:
        await session.begin()
        try:
            yield session
        finally:
            await session.rollback()


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
