"""Regression tests for the `ingestion_worker_supervisor` lifecycle contract.

Two invariants are pinned here:

1. The supervisor MUST forward `shutdown_graceful_timeout` to Procrastinate's
   `run_worker_async` — without it `_shutdown` waits forever for an in-flight job,
   so a reload mid-cycle hangs the process (the original `--reload` hang fix).
2. The supervisor MUST restart the worker when `run_worker_async` returns
   *normally* — Procrastinate self-stops (returns, does not raise) when a side task
   like the DB heartbeat fails on a transient connection drop (a Postgres restart /
   Fly-proxy recycle). Only cancellation (lifespan teardown) may end the loop.
   The old `return # graceful shutdown` let a routine PG blip permanently kill the
   worker — and with it the reaper, scheduler, and alert-evaluator (all Procrastinate
   tasks), invisibly to Fly's HTTP-only health check.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from app.core.config import get_settings
from app.ingestion import procrastinate_app
from app.ingestion.worker import ingestion_worker_supervisor


@pytest.mark.asyncio
async def test_supervisor_passes_shutdown_graceful_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    async def fake_run_worker_async(**kwargs: Any) -> None:
        captured.update(kwargs)
        # Cancellation is the one clean exit — stand in for the lifespan teardown
        # cancelling the supervisor task, so the loop stops after one iteration.
        raise asyncio.CancelledError

    monkeypatch.setattr(procrastinate_app, "run_worker_async", fake_run_worker_async)

    with pytest.raises(asyncio.CancelledError):
        await ingestion_worker_supervisor()

    settings = get_settings()
    assert "shutdown_graceful_timeout" in captured
    assert captured["shutdown_graceful_timeout"] == settings.ingestion_worker_shutdown_timeout_s
    # The supervisor still owns the signal handlers (FastAPI does) + the queue set.
    assert captured["install_signal_handlers"] is False


@pytest.mark.asyncio
async def test_supervisor_restarts_on_self_stop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A normal return from `run_worker_async` (Procrastinate self-stop) restarts
    the worker; only `CancelledError` ends the loop. Fails on the old `return`."""
    calls = 0

    async def fake_run_worker_async(**_kwargs: Any) -> None:
        nonlocal calls
        calls += 1
        if calls >= 3:
            # After two restarts, stand in for lifespan teardown.
            raise asyncio.CancelledError
        # Return normally → Procrastinate self-stopped on a side-task failure.

    # Don't actually wait out the restart backoff in the test.
    async def instant_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr(procrastinate_app, "run_worker_async", fake_run_worker_async)
    monkeypatch.setattr("app.ingestion.worker.asyncio.sleep", instant_sleep)

    with pytest.raises(asyncio.CancelledError):
        await ingestion_worker_supervisor()

    # Two normal returns were restarted; the third call cancelled out.
    assert calls == 3
