"""The migration lock must not block what a migration runs.

`CREATE INDEX CONCURRENTLY` waits for older transactions to finish. That includes a
holder sitting in an open transaction, and a session blocked in `pg_advisory_lock`
waiting for its turn. Neither finishes until the migration does, so the boot hangs
forever and the API never reports healthy. Postgres can't see it as a deadlock, since
the session holding the lock isn't the one building the index.
"""

from __future__ import annotations

import asyncio
import time
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
_WAITER_ARRIVAL_S = 1.0


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


@pytest.mark.asyncio
async def test_a_process_waiting_for_the_lock_does_not_block_the_migration(
    db_engine: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two processes boot together: one migrates, the other waits and then no-ops."""
    url = db_engine.url.render_as_string(hide_password=False)
    runs: list[int] = []

    def migrate() -> None:
        # Only the first holder has work to do, as with alembic reaching head.
        runs.append(1)
        if len(runs) == 1:
            time.sleep(_WAITER_ARRIVAL_S)
            asyncio.run(_build_index_concurrently(url))

    monkeypatch.setattr(startup, "get_settings", lambda: SimpleNamespace(database_url=url))
    monkeypatch.setattr(startup, "_run_migrations_sync", migrate)

    await asyncio.wait_for(
        asyncio.gather(startup._run_migrations_locked(), startup._run_migrations_locked()),  # pyright: ignore[reportPrivateUsage]
        _TEST_BOUND_S,
    )

    assert len(runs) == 2
