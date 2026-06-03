"""Regression test for the boot-time Procrastinate schema apply guard.

Bug: `apply_procrastinate_schema_locked()` called `apply_schema_async()` unconditionally.
Procrastinate's schema SQL is raw `CREATE TYPE` / `CREATE TABLE` (no `IF NOT EXISTS`), so on
any boot after the first it raised `type "procrastinate_job_status" already exists`. That
exception was swallowed by the `contextlib.suppress(Exception)` in `app/main.py`, so the
ingestion worker silently never started on restarts. The fix guards on `to_regclass` and only
applies when the schema is absent.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any
from unittest.mock import AsyncMock

import pytest
from procrastinate.schema import SchemaManager

from app.ingestion import worker


class _FakeResult:
    def __init__(self, scalar_value: Any) -> None:
        self._scalar_value = scalar_value

    def scalar(self) -> Any:
        return self._scalar_value


class _FakeSession:
    """Minimal async session stub. `to_regclass` returns the configured value."""

    def __init__(self, regclass_value: Any) -> None:
        self._regclass_value = regclass_value
        self.commit = AsyncMock()
        self.close = AsyncMock()

    async def execute(self, statement: Any, *_: Any, **__: Any) -> _FakeResult:
        # Only the to_regclass SELECT consults .scalar(); lock/unlock ignore it.
        return _FakeResult(self._regclass_value)


def _patch_session_factory(monkeypatch: pytest.MonkeyPatch, regclass_value: Any) -> None:
    session = _FakeSession(regclass_value)

    @asynccontextmanager
    async def _factory() -> AsyncGenerator[_FakeSession]:
        yield session

    monkeypatch.setattr(worker, "AsyncSessionLocal", _factory)


@pytest.fixture
def apply_mock(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    """Patch the (property-minted, so patched at the class) schema-apply call."""
    mock = AsyncMock()
    monkeypatch.setattr(SchemaManager, "apply_schema_async", mock)
    return mock


@pytest.mark.asyncio
async def test_skips_apply_when_schema_already_present(
    monkeypatch: pytest.MonkeyPatch, apply_mock: AsyncMock
) -> None:
    # to_regclass('procrastinate_jobs') resolves → schema already there → must NOT re-apply.
    _patch_session_factory(monkeypatch, regclass_value="procrastinate_jobs")

    await worker.apply_procrastinate_schema_locked()

    apply_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_applies_when_schema_absent(
    monkeypatch: pytest.MonkeyPatch, apply_mock: AsyncMock
) -> None:
    # to_regclass returns NULL → first boot → apply the schema.
    _patch_session_factory(monkeypatch, regclass_value=None)

    await worker.apply_procrastinate_schema_locked()

    apply_mock.assert_awaited_once()
