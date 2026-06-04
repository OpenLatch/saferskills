"""Crash-resilience Fix A — connection budget + fail-fast back-pressure.

Covers the two behaviours the addendum (`plan/04-crash-resilience-hardening.md`)
adds so the in-process ingestion worker can never silently exhaust the shared
SQLAlchemy pool the public API serves from:

  §1.5 — the worker REFUSES to start if `ingestion_worker_concurrency` could
         drain the pool (`>= db_pool_size + db_max_overflow`).
  §1.3 — a pool-checkout `TimeoutError` is mapped to a bounded **503** instead
         of hanging the request until the worker frees a slot.
"""

from __future__ import annotations

import json

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.exc import TimeoutError as SQLAlchemyTimeoutError

from app.core.config import Settings
from app.db.session import get_session
from app.ingestion import worker
from app.main import app

# ── §1.5 — startup concurrency-vs-pool assertion ────────────────────────────


def test_worker_budget_rejects_concurrency_that_could_drain_the_pool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """concurrency == pool+overflow leaves zero API headroom → refuse to boot."""
    bad = Settings(ingestion_worker_concurrency=15, db_pool_size=5, db_max_overflow=10)
    monkeypatch.setattr(worker, "get_settings", lambda: bad)
    with pytest.raises(RuntimeError, match="leave SQLAlchemy headroom"):
        worker.assert_worker_concurrency_budget()


def test_worker_budget_accepts_the_default_headroom(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Default 4 + 4 vs 5+10 leaves ≥7 slots for the API → boots fine."""
    ok = Settings(
        ingestion_worker_concurrency=4, scan_max_concurrency=4, db_pool_size=5, db_max_overflow=10
    )
    monkeypatch.setattr(worker, "get_settings", lambda: ok)
    worker.assert_worker_concurrency_budget()  # must not raise


def test_worker_budget_counts_scan_concurrency(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The durable scan budget is part of the sum: 4 + 11 == 15 leaves no headroom."""
    bad = Settings(
        ingestion_worker_concurrency=4,
        scan_max_concurrency=11,
        db_pool_size=5,
        db_max_overflow=10,
    )
    monkeypatch.setattr(worker, "get_settings", lambda: bad)
    with pytest.raises(RuntimeError, match="leave"):
        worker.assert_worker_concurrency_budget()


# ── §1.3 — pool-timeout back-pressure → 503, never a hang ───────────────────


@pytest.mark.asyncio
async def test_pool_timeout_returns_bounded_503() -> None:
    """A SQLAlchemy pool-checkout timeout surfaces as a clean 503, not a 500/hang.

    Override `get_session` to raise the exact exception `pool_timeout` raises;
    assert the registered handler maps it to the bounded back-pressure response.
    """

    async def _raise_pool_timeout() -> None:
        raise SQLAlchemyTimeoutError("QueuePool limit of size 5 overflow 10 reached")

    app.dependency_overrides[get_session] = _raise_pool_timeout
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get("/api/v1/items/facets")
    finally:
        app.dependency_overrides.pop(get_session, None)

    assert resp.status_code == 503
    body = json.loads(resp.content)
    assert body["detail"]["code"] == "SERVICE_UNAVAILABLE"
