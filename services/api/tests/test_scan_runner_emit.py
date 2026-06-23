"""Regression: a missing/broken asyncpg NOTIFY pool must NOT abort a scan.

The asyncpg LISTEN/NOTIFY pool (`app/core/db_pool.py`) is used by `_emit` ONLY
for the live SSE delta (`pg_notify`). The durable progress record is the
`scan_events` row committed via SQLAlchemy *before* the notify; the SSE consumer
(`routers/scans.py::scan_events`) already replays those rows and tolerates a
missing pool (`except RuntimeError: return`). When the pool failed to initialize
in production (a `sslmode=disable` DSN whose `ssl=` form raw asyncpg rejected),
`_emit` raised at `get_pool()` on the very first progress event — so every
interactive/upload scan died before any work and surfaced as `status='failed'`
with nothing persisted ("scan results not available"). The notify must degrade
to "no live deltas", never abort the scan.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.queue import scan_runner


class _FakeResult:
    def scalar_one(self) -> int:
        return 0


class _FakeSession:
    """Stand-in for the AsyncSession `_emit` opens — the DB write is not under
    test here, only that a failed NOTIFY pool does not propagate."""

    async def execute(self, *_args: object, **_kwargs: object) -> _FakeResult:
        return _FakeResult()

    def add(self, _obj: object) -> None:
        pass

    async def commit(self) -> None:
        pass


class _FakeSessionCtx:
    async def __aenter__(self) -> _FakeSession:
        return _FakeSession()

    async def __aexit__(self, *_args: object) -> None:
        pass


@pytest.mark.asyncio
async def test_emit_does_not_raise_when_notify_pool_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(scan_runner, "AsyncSessionLocal", lambda: _FakeSessionCtx())

    def _no_pool() -> object:
        raise RuntimeError(
            "asyncpg pool not initialized — ensure lifespan startup ran init_pool()."
        )

    monkeypatch.setattr(scan_runner, "get_pool", _no_pool)

    # Must complete without raising — the committed scan_events row is the durable
    # progress; the NOTIFY is best-effort.
    await scan_runner._emit(  # pyright: ignore[reportPrivateUsage]
        uuid4(),
        "fetch",
        5,
        "running",
        {"target": "upload"},
        scan_run_id=uuid4(),
    )
