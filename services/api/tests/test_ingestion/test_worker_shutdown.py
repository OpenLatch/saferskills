"""Regression test pinning the primary fix for the `--reload` ingestion hang.

`ingestion_worker_supervisor` MUST pass `shutdown_graceful_timeout` to
Procrastinate's `run_worker_async` — without it `_shutdown` waits forever for an
in-flight job, so a reload mid-cycle hangs the process. This test captures the
kwargs the supervisor forwards and asserts the knob is present + sourced from the
`ingestion_worker_shutdown_timeout_s` setting, so a future edit can't silently
drop it.
"""

from __future__ import annotations

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
        # Return immediately → supervisor takes its graceful-shutdown `return`.

    monkeypatch.setattr(procrastinate_app, "run_worker_async", fake_run_worker_async)

    await ingestion_worker_supervisor()

    settings = get_settings()
    assert "shutdown_graceful_timeout" in captured
    assert captured["shutdown_graceful_timeout"] == settings.ingestion_worker_shutdown_timeout_s
    # The supervisor still owns the signal handlers (FastAPI does) + the queue set.
    assert captured["install_signal_handlers"] is False
