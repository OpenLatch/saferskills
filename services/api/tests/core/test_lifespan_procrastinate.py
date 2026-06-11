"""Regression tests for the FastAPI lifespan's Procrastinate wiring.

Pins the worker-split defer-path contract: the Procrastinate connector must be
opened (+ schema applied) whenever the API is healthy, EVEN when this process
does not run the worker (`INGESTION_WORKER_ENABLED=false`). Otherwise the API's
own defer paths — webhook dispatch, admin force-cycle, popularity recompute —
500 with a closed connector. The in-process supervisor starts only when the
worker is enabled.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.config import get_settings
from app.core.startup_state import startup_state
from app.main import app, lifespan


@asynccontextmanager
async def _patched_lifespan(
    monkeypatch: pytest.MonkeyPatch, *, worker_enabled: bool
) -> AsyncIterator[dict[str, MagicMock]]:
    """Drive the real lifespan with every external touchpoint mocked.

    Yields the mocks of interest so a test can assert how the Procrastinate
    block behaved for the given worker_enabled setting.
    """
    import app.core.sweeps as sweeps_mod
    import app.ingestion as ingestion_mod
    import app.ingestion.tasks as tasks_mod
    import app.ingestion.worker as worker_mod
    import app.main as main_mod
    import app.queue.scan_runner as scan_runner_mod
    from app.routers import scans as scans_mod

    monkeypatch.setattr(get_settings(), "ingestion_worker_enabled", worker_enabled)

    # Force a healthy boot without touching the DB.
    prev_ok = startup_state.migrations_ok
    prev_degraded = startup_state.ingestion_degraded
    startup_state.mark_migrations_ok()
    startup_state.ingestion_degraded = False

    # Boot touchpoints → inert.
    monkeypatch.setattr(main_mod, "init_observability", AsyncMock())
    monkeypatch.setattr(main_mod, "run_startup", AsyncMock())
    monkeypatch.setattr(main_mod, "init_pool", AsyncMock())
    monkeypatch.setattr(main_mod, "close_pool", AsyncMock())
    monkeypatch.setattr(main_mod, "shutdown_observability", MagicMock())
    monkeypatch.setattr(scan_runner_mod, "recover_stale_scans", AsyncMock())
    monkeypatch.setattr(tasks_mod, "recover_stale_ingestion_runs", AsyncMock())

    async def _never() -> None:  # the sweep loop — cancelled at teardown
        import asyncio

        await asyncio.Event().wait()

    monkeypatch.setattr(sweeps_mod, "run_sweep_loop", _never)
    monkeypatch.setattr(scans_mod, "cancel_background_scans", AsyncMock())

    # Procrastinate touchpoints — the unit under test.
    open_async = AsyncMock()
    apply_schema = AsyncMock()
    supervisor = AsyncMock()
    budget = MagicMock()
    monkeypatch.setattr(ingestion_mod.procrastinate_app, "open_async", open_async)
    monkeypatch.setattr(ingestion_mod.procrastinate_app, "close_async", AsyncMock())
    monkeypatch.setattr(worker_mod, "apply_procrastinate_schema_locked", apply_schema)
    monkeypatch.setattr(worker_mod, "ingestion_worker_supervisor", supervisor)
    monkeypatch.setattr(worker_mod, "assert_worker_concurrency_budget", budget)

    try:
        async with lifespan(app):
            yield {
                "open_async": open_async,
                "apply_schema": apply_schema,
                "supervisor": supervisor,
                "budget": budget,
            }
    finally:
        startup_state.migrations_ok = prev_ok
        startup_state.ingestion_degraded = prev_degraded


@pytest.mark.asyncio
async def test_defer_connector_opens_with_worker_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Worker OFF: connector still opens + schema applies (defer paths live), but
    the supervisor is NOT started. FAILS on main (open_async was worker-gated)."""
    async with _patched_lifespan(monkeypatch, worker_enabled=False) as mocks:
        mocks["open_async"].assert_awaited_once()
        mocks["apply_schema"].assert_awaited_once()
        mocks["supervisor"].assert_not_called()
        assert not startup_state.ingestion_degraded


@pytest.mark.asyncio
async def test_worker_starts_when_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    """Worker ON: connector opens, budget asserted, supervisor started."""
    async with _patched_lifespan(monkeypatch, worker_enabled=True) as mocks:
        mocks["open_async"].assert_awaited_once()
        mocks["apply_schema"].assert_awaited_once()
        mocks["budget"].assert_called_once()
        mocks["supervisor"].assert_called_once()
