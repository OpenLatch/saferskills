"""The migration lock holder must not block what a migration runs.

`CREATE INDEX CONCURRENTLY` waits for older transactions to finish. A lock holder
sitting in an open transaction only finishes after the migration does, so the boot
hangs forever and the API never reports healthy.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.core import startup

# The migration stand-in fails on its own well before the test's overall bound, so a
# regression reports the cancelled statement instead of an unexplained timeout.
_INDEX_TIMEOUT = "10s"
_TEST_BOUND_S = 30


async def _build_index_concurrently(url: str) -> None:
    engine = create_async_engine(url, isolation_level="AUTOCOMMIT", poolclass=NullPool)
    try:
        async with engine.connect() as conn:
            await conn.execute(text("CREATE TABLE IF NOT EXISTS _migration_lock_probe (x int)"))
            try:
                await conn.execute(text(f"SET statement_timeout = '{_INDEX_TIMEOUT}'"))
                await conn.execute(
                    text(
                        "CREATE INDEX CONCURRENTLY idx_migration_lock_probe "
                        "ON _migration_lock_probe (x)"
                    )
                )
            finally:
                await conn.execute(text("DROP TABLE _migration_lock_probe"))
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_migration_can_create_index_concurrently_under_the_lock(
    db_engine: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    url = db_engine.url.render_as_string(hide_password=False)
    monkeypatch.setattr(startup, "get_settings", lambda: SimpleNamespace(database_url=url))
    monkeypatch.setattr(
        startup, "_run_migrations_sync", lambda: asyncio.run(_build_index_concurrently(url))
    )

    await asyncio.wait_for(startup._run_migrations_locked(), _TEST_BOUND_S)  # pyright: ignore[reportPrivateUsage]
