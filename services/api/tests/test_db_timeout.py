"""WS1 — API fast-fail under DB pressure (engine statement-timeout).

Proves the three layers of the per-query bound:
  1. `engine_connect_args` carries `statement_timeout` (+ idle-in-txn) and omits
     a disabled knob — a pure unit test, no DB.
  2. A live `SELECT pg_sleep(N)` against a 1 s-statement_timeout engine is ABORTED
     at ~1 s (SQLSTATE 57014), NOT after N s — proving Postgres frees the
     connection instead of hanging.
  3. `_statement_timeout_handler` maps that real cancellation to a bounded 503, and
     re-raises a genuine (non-pressure) `DBAPIError` so it still 500s.

The handler/abort tests build their OWN engine pointed at the test DB so they
never touch the shared app engine or the migration path (alembic uses a separate
engine — asserted indirectly: these timeouts are connect_args on this engine only).
"""

from __future__ import annotations

import time
from typing import cast

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from starlette.requests import Request

from app.core.config import get_settings
from app.db.session import engine_connect_args
from app.main import _statement_timeout_handler  # pyright: ignore[reportPrivateUsage]


def _dummy_request() -> Request:
    """A minimal HTTP Request — the handler ignores it (it only reads the exc)."""
    return Request({"type": "http", "method": "GET", "headers": []})


def test_engine_connect_args_carries_statement_timeout() -> None:
    settings = get_settings().model_copy(
        update={"db_statement_timeout_s": 30, "db_command_timeout_s": 0.0}
    )
    args = engine_connect_args(settings)
    server_settings = cast(dict[str, str], args["server_settings"])
    assert server_settings["statement_timeout"] == "30000"
    assert server_settings["idle_in_transaction_session_timeout"] == "30000"
    # command_timeout disabled (0) → omitted entirely.
    assert "command_timeout" not in args


def test_engine_connect_args_disabled_and_command_timeout() -> None:
    # statement_timeout 0 → no server_settings at all.
    s_off = get_settings().model_copy(
        update={"db_statement_timeout_s": 0, "db_command_timeout_s": 0.0}
    )
    assert engine_connect_args(s_off) == {}

    # command_timeout > 0 is the only knob → just that key.
    s_cmd = get_settings().model_copy(
        update={"db_statement_timeout_s": 0, "db_command_timeout_s": 5.0}
    )
    assert engine_connect_args(s_cmd) == {"command_timeout": 5.0}


@pytest.mark.asyncio
async def test_statement_timeout_aborts_slow_query(db_engine: object) -> None:
    """A 5 s query on a 1 s-statement_timeout engine is ABORTED at ~1 s (57014)."""
    url = cast(AsyncEngine, db_engine).url.render_as_string(hide_password=False)
    settings = get_settings().model_copy(
        update={"db_statement_timeout_s": 1, "db_command_timeout_s": 0.0}
    )
    eng = create_async_engine(url, connect_args=engine_connect_args(settings))
    start = time.monotonic()
    try:
        with pytest.raises(DBAPIError) as excinfo:
            async with eng.connect() as conn:
                await conn.execute(text("SELECT pg_sleep(5)"))
        elapsed = time.monotonic() - start
    finally:
        await eng.dispose()

    # Bounded by the 1 s statement_timeout, NOT the 5 s sleep.
    assert elapsed < 4, f"slow query was not bounded (took {elapsed:.1f}s)"
    orig = getattr(excinfo.value, "orig", None)
    assert getattr(orig, "sqlstate", None) == "57014"  # query_canceled


@pytest.mark.asyncio
async def test_handler_maps_real_statement_timeout_to_503(db_engine: object) -> None:
    """The handler turns a real statement-timeout cancellation into a bounded 503."""
    url = cast(AsyncEngine, db_engine).url.render_as_string(hide_password=False)
    settings = get_settings().model_copy(
        update={"db_statement_timeout_s": 1, "db_command_timeout_s": 0.0}
    )
    eng = create_async_engine(url, connect_args=engine_connect_args(settings))
    real_exc: DBAPIError | None = None
    try:
        async with eng.connect() as conn:
            await conn.execute(text("SELECT pg_sleep(3)"))
    except DBAPIError as exc:
        real_exc = exc
    finally:
        await eng.dispose()

    assert real_exc is not None
    resp = await _statement_timeout_handler(_dummy_request(), real_exc)
    assert resp.status_code == 503


@pytest.mark.asyncio
async def test_handler_reraises_non_pressure_dbapierror(db_engine: object) -> None:
    """A genuine (non-pressure) DBAPIError is re-raised → still a 500 + Sentry."""
    url = cast(AsyncEngine, db_engine).url.render_as_string(hide_password=False)
    eng = create_async_engine(url)
    real_exc: DBAPIError | None = None
    try:
        async with eng.connect() as conn:
            await conn.execute(text("SELECT * FROM _saferskills_nonexistent_table_xyz"))
    except DBAPIError as exc:
        real_exc = exc
    finally:
        await eng.dispose()

    assert real_exc is not None  # undefined_table 42P01 — not a DB-pressure SQLSTATE
    with pytest.raises(DBAPIError):
        await _statement_timeout_handler(_dummy_request(), real_exc)
