"""The scan-job + ingestion-cycle paths emit a `memory.rss_mb` structlog event.

Memory observability: a creeping RSS (the OOM-loop signal on a small machine)
must be visible per scan job and per ingestion cycle without a metrics pipeline.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from structlog.testing import capture_logs


@pytest.mark.asyncio
async def test_scan_job_emits_rss_log(monkeypatch: pytest.MonkeyPatch) -> None:
    """scan_capability_repo logs memory.rss_mb (context=scan_job) on success."""
    from app.ingestion import tasks_scan

    monkeypatch.setattr(
        tasks_scan, "execute_scan", AsyncMock(return_value={"action": "scan", "reason": "x"})
    )
    monkeypatch.setattr(tasks_scan, "rss_mb", lambda: 123.4)

    with capture_logs() as logs:
        result = await tasks_scan.scan_capability_repo("https://github.com/acme/repo")

    assert result["action"] == "scan"
    rss_events = [e for e in logs if e.get("event") == "memory.rss_mb"]
    assert len(rss_events) == 1
    assert rss_events[0]["context"] == "scan_job"
    assert rss_events[0]["rss_mb"] == 123.4


@pytest.mark.asyncio
async def test_cycle_emits_rss_log(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A successful run_source_cycle logs memory.rss_mb (context=ingestion_cycle)."""
    from app.core import config as config_module
    from app.db import session as session_module
    from app.ingestion import tasks as tasks_module
    from app.ingestion.config.loader import get_source_config
    from app.ingestion.sources.smithery import SmitheryAdapter
    from app.ingestion.tasks import run_source_cycle

    monkeypatch.setattr(config_module.get_settings(), "ingestion_source_blocklist", [])
    monkeypatch.setattr(tasks_module, "rss_mb", lambda: 222.5)

    counters: dict[str, Any] = {
        "items_seen": 3,
        "items_added": 1,
        "items_updated": 0,
        "items_skipped": 0,
        "http_304_count": 0,
        "http_5xx_count": 0,
    }
    adapter = SmitheryAdapter(get_source_config("smithery"))
    adapter.run_cycle = AsyncMock(return_value=counters)  # type: ignore[method-assign]

    def _build(_name: str) -> SmitheryAdapter:
        return adapter

    monkeypatch.setattr(tasks_module, "build_adapter", _build)

    class _FakeCtx:
        async def __aenter__(self) -> AsyncSession:
            return db_session

        async def __aexit__(self, *args: object) -> None:
            pass

    monkeypatch.setattr(session_module, "AsyncSessionLocal", lambda: _FakeCtx())

    with capture_logs() as logs:
        result = await run_source_cycle("smithery")

    assert result == counters
    rss_events = [e for e in logs if e.get("event") == "memory.rss_mb"]
    assert len(rss_events) == 1
    assert rss_events[0]["context"] == "ingestion_cycle"
    assert rss_events[0]["rss_mb"] == 222.5
