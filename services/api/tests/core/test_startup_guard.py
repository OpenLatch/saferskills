"""Tests for the degraded-mode startup guard + startup-state singleton.

No live DB needed — the FastAPI lifespan never fires under httpx's
`ASGITransport`, so these tests drive `startup_state` directly and assert how
`StartupGuardMiddleware` (wired in `app.main`) responds. The root conftest's
autouse `_migrations_ok` fixture saves/restores the singleton around each test.
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.startup_state import (
    _StartupState,  # pyright: ignore[reportPrivateUsage]
    startup_state,
)
from app.main import app


def test_startup_state_transitions() -> None:
    state = _StartupState()
    assert state.migrations_ok is False
    assert state.migrations_error is None
    assert state.is_healthy is False

    state.mark_migrations_failed("boom")
    assert state.migrations_ok is False
    assert state.migrations_error == "boom"
    assert state.is_healthy is False

    state.mark_migrations_ok()
    assert state.migrations_ok is True
    assert state.migrations_error is None
    assert state.is_healthy is True


@pytest.mark.asyncio
async def test_guard_passes_through_when_healthy() -> None:
    """Healthy state (set by the autouse fixture) lets any route through."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/health")
    assert resp.status_code == 200
    assert resp.json()["migrations_ok"] is True


@pytest.mark.asyncio
async def test_guard_503_on_normal_route_when_degraded() -> None:
    startup_state.mark_migrations_failed("alembic upgrade head failed")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/stats")
    assert resp.status_code == 503
    body = resp.json()
    assert body["detail"]["code"] == "SERVICE_UNAVAILABLE"
    assert "degraded" in body["detail"]["message"].lower()


@pytest.mark.asyncio
async def test_guard_bypasses_health_when_degraded() -> None:
    """`/api/v1/health` must stay reachable so ops can read the failure cause."""
    startup_state.mark_migrations_failed("alembic upgrade head failed")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["migrations_ok"] is False
    assert body["migrations_error"] == "alembic upgrade head failed"
