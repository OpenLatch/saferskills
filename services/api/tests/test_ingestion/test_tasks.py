"""Tests for app.ingestion.tasks.run_source_cycle — blocklist + paused + blocked paths."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CrawlerCursor


@pytest.mark.asyncio
async def test_run_source_cycle_skips_blocklisted_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A source in ingestion_source_blocklist must be skipped immediately."""
    from app.core import config as config_module
    from app.ingestion.tasks import run_source_cycle

    monkeypatch.setattr(
        config_module.get_settings(), "ingestion_source_blocklist", ["github_topics"]
    )
    result = await run_source_cycle("github_topics")
    assert result == {"skipped": "blocklist"}


@pytest.mark.asyncio
async def test_run_source_cycle_skips_paused_source(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A paused source should return {skipped: paused} without running a cycle."""

    from app.core import config as config_module
    from app.db import session as session_module
    from app.ingestion.tasks import run_source_cycle

    # Ensure source is not in blocklist
    monkeypatch.setattr(config_module.get_settings(), "ingestion_source_blocklist", [])

    # Set the github_topics cursor to paused
    await db_session.execute(
        update(CrawlerCursor).where(CrawlerCursor.source == "github_topics").values(status="paused")
    )
    await db_session.flush()

    # Patch AsyncSessionLocal to use the test session (which has the paused row)

    class _FakeCtx:
        async def __aenter__(self) -> AsyncSession:
            return db_session

        async def __aexit__(self, *args: object) -> None:
            pass

    monkeypatch.setattr(session_module, "AsyncSessionLocal", lambda: _FakeCtx())

    result = await run_source_cycle("github_topics")
    assert result == {"skipped": "paused"}


@pytest.mark.asyncio
async def test_run_source_cycle_blocked_on_cloudflare(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An AdapterBlockedError (Cloudflare challenge) flips the source to `blocked`,
    records the failure, and returns {skipped: blocked} WITHOUT re-raising (no retry
    storm). This is the lean-stack terminal path (no Playwright tier)."""
    from app.core import config as config_module
    from app.db import session as session_module
    from app.ingestion import tasks as tasks_module
    from app.ingestion.config.loader import get_source_config
    from app.ingestion.framework.exceptions import AdapterBlockedError
    from app.ingestion.sources.smithery import SmitheryAdapter
    from app.ingestion.tasks import run_source_cycle

    monkeypatch.setattr(config_module.get_settings(), "ingestion_source_blocklist", [])

    adapter = SmitheryAdapter(get_source_config("smithery"))
    adapter.run_cycle = AsyncMock(side_effect=AdapterBlockedError("cf challenge"))  # type: ignore[method-assign]

    def _build(_name: str) -> SmitheryAdapter:
        return adapter

    monkeypatch.setattr(tasks_module, "build_adapter", _build)

    class _FakeCtx:
        async def __aenter__(self) -> AsyncSession:
            return db_session

        async def __aexit__(self, *args: object) -> None:
            pass

    monkeypatch.setattr(session_module, "AsyncSessionLocal", lambda: _FakeCtx())

    result = await run_source_cycle("smithery")
    assert result == {"skipped": "blocked"}

    status = (
        await db_session.execute(
            select(CrawlerCursor.status).where(CrawlerCursor.source == "smithery")
        )
    ).scalar_one()
    assert status == "blocked"
