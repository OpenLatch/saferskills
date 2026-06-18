"""Migration 0019 upgrade↔downgrade smoke.

The session-scoped `db_engine` fixture already proves `alembic upgrade head`
(which includes 0019). This exercises the DOWNGRADE path: roll back the single
0019 revision then re-apply it, leaving the DB at head for the rest of the suite.
Runs in a subprocess so alembic owns its own event loop (mirrors conftest).
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import pytest

_API_ROOT = Path(__file__).resolve().parents[1]


def _db_url() -> str:
    explicit = os.environ.get("DATABASE_URL_TEST")
    if explicit:
        return explicit
    dev = os.environ.get(
        "DATABASE_URL", "postgresql+asyncpg://postgres:dev@localhost:5432/saferskills_dev"
    )
    return dev if dev.endswith("_test") else f"{dev}_test"


async def _alembic(*args: str) -> int:
    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "alembic",
        *args,
        cwd=str(_API_ROOT),
        env={**os.environ, "DATABASE_URL": _db_url()},
    )
    return await proc.wait()


@pytest.mark.asyncio
async def test_0019_downgrade_then_upgrade(db_engine: object) -> None:
    # db_engine ensures head is applied + the DB exists. Roll 0019 back + forward.
    assert await _alembic("downgrade", "0018_scan_install_spec") == 0
    assert await _alembic("upgrade", "head") == 0
