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


@pytest.mark.asyncio
async def test_run_source_cycle_provider_failure_warns_no_raise(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A provider/transport failure (e.g. a GitHub 403 rate limit) is an OPERATIONAL
    event, not a bug: the cycle must emit a clean WARN (no stack trace), record the
    failed run, and return WITHOUT re-raising — so neither our logger nor Procrastinate
    dumps a traceback, and no pointless fast-retry storm is triggered. The source must
    NOT be flipped to `blocked` (that is the Cloudflare-only terminal path)."""
    import httpx

    from app.core import config as config_module
    from app.db import session as session_module
    from app.ingestion import tasks as tasks_module
    from app.ingestion.config.loader import get_source_config
    from app.ingestion.sources.smithery import SmitheryAdapter
    from app.ingestion.tasks import run_source_cycle

    monkeypatch.setattr(config_module.get_settings(), "ingestion_source_blocklist", [])

    request = httpx.Request("GET", "https://api.github.com/search/repositories")
    response = httpx.Response(403, request=request)
    adapter = SmitheryAdapter(get_source_config("smithery"))
    adapter.run_cycle = AsyncMock(  # type: ignore[method-assign]
        side_effect=httpx.HTTPStatusError("rate limited", request=request, response=response)
    )

    def _build(_name: str) -> SmitheryAdapter:
        return adapter

    monkeypatch.setattr(tasks_module, "build_adapter", _build)

    class _FakeCtx:
        async def __aenter__(self) -> AsyncSession:
            return db_session

        async def __aexit__(self, *args: object) -> None:
            pass

    monkeypatch.setattr(session_module, "AsyncSessionLocal", lambda: _FakeCtx())

    # Must NOT raise (regression: previously `logger.exception` + `raise` dumped a
    # traceback and triggered a retry storm).
    result = await run_source_cycle("smithery")
    assert result == {"skipped": "failed", "reason": "rate_limit"}

    # Not flipped to `blocked` — that is the Cloudflare-only terminal path.
    status = (
        await db_session.execute(
            select(CrawlerCursor.status).where(CrawlerCursor.source == "smithery")
        )
    ).scalar_one()
    assert status != "blocked"


def test_ingest_cycle_tasks_outrank_fanout_and_dedup_per_source() -> None:
    """Every cadenced ingest_cycle_* task must register with a priority above the
    bulk auto-scan/popularity fan-out (priority 0) AND a per-source queueing_lock.

    Regression for the worker-starvation bug: without the priority bump the single
    in-process worker fetches `priority DESC, id ASC`, so each scheduled cycle is
    buried inside the thousands-deep scan/recompute fan-out id-band and effectively
    never runs (sources stuck `never_run`); without the per-source queueing_lock an
    hourly cadence stacks a second crawl behind an in-flight one (the npm-pileup /
    mcp_registry-zombie-stacking bug).
    """
    import app.ingestion.tasks  # noqa: F401  # side-effect: registers periodic tasks
    from app.ingestion import INGEST_CYCLE_PRIORITY, procrastinate_app

    cycles = {
        name: t for name, t in procrastinate_app.tasks.items() if name.startswith("ingest_cycle_")
    }
    assert cycles, "no ingest_cycle_* tasks registered"
    assert INGEST_CYCLE_PRIORITY > 0  # must beat the priority-0 fan-out

    for name, task in cycles.items():
        source = name.removeprefix("ingest_cycle_")
        assert task.priority == INGEST_CYCLE_PRIORITY, f"{name} priority not bumped"
        assert task.queueing_lock == f"ingest_cycle_{source}_lock", (
            f"{name} missing per-source lock"
        )
