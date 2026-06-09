"""SAVEPOINT-isolated session for the DB-backed agent-scan tests.

The telemetry writer + the sweeps call `session.commit()`. Under the root
`db_session` (a plain begin/rollback) those commits ESCAPE the rollback and leak
rows across runs. Mirroring the routers' `join_transaction_mode="create_savepoint"`
session makes each commit a SAVEPOINT release inside one outer transaction that is
rolled back at teardown — so no test data ever escapes.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession


@pytest_asyncio.fixture
async def db_session(db_engine: Any) -> AsyncIterator[AsyncSession]:
    async with db_engine.connect() as conn:  # pyright: ignore[reportUnknownMemberType]
        outer = await conn.begin()
        session = AsyncSession(
            bind=conn,
            join_transaction_mode="create_savepoint",
            expire_on_commit=False,
        )
        try:
            yield session
        finally:
            await session.close()
            await outer.rollback()
