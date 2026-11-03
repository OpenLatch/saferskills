"""Record the SQL a block of code runs on a test session's connection.

Regression guards assert on query shape (which tables a read touches) rather than
on plans, which are unstable on small test tables.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession


@asynccontextmanager
async def capture_sql(session: AsyncSession) -> AsyncGenerator[list[str]]:
    connection = (await session.connection()).sync_connection
    assert connection is not None
    statements: list[str] = []

    def _record(
        _conn: Any, _cursor: Any, statement: str, _params: Any, _context: Any, _many: Any
    ) -> None:
        statements.append(statement)

    event.listen(connection, "before_cursor_execute", _record)
    try:
        yield statements
    finally:
        event.remove(connection, "before_cursor_execute", _record)
