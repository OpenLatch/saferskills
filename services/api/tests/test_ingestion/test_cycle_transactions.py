"""The runner must release its pause-check transaction before provider I/O."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any, cast
from unittest.mock import AsyncMock, Mock
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.ingestion.framework.base_adapter import RawItem
from app.models import IngestionEvent, IngestionRun


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [None, "provider", "unexpected"])
async def test_clawhub_fetch_releases_preflight_transaction(
    db_engine: object, monkeypatch: pytest.MonkeyPatch, failure: str | None
) -> None:
    """Real pause SELECT and durable run/outbox writes; provider I/O is mocked.

    Checking every opened session at the first provider fetch catches the idle
    transaction without waiting for the production 30-second timeout to kill it.
    Both expected and unexpected fetch failures must retain a failed run record.
    """
    from app.core.config import get_settings
    from app.db import session as session_module
    from app.ingestion import tasks
    from app.ingestion.framework.http_client import HttpClientFactory
    from app.ingestion.sources.clawhub import ClawhubAdapter

    factory = async_sessionmaker(cast(AsyncEngine, db_engine), expire_on_commit=False)
    sessions: list[AsyncSession] = []
    run_ids: list[UUID] = []
    source_id = f"transaction-regression-{uuid4()}"
    pause_checked = False
    original_pause_check = tasks.is_source_paused
    original_record_started = tasks.record_run_started

    def tracked_session() -> AsyncSession:
        session = factory()
        sessions.append(session)
        return session

    async def check_pause(session: AsyncSession, source: str) -> bool:
        nonlocal pause_checked
        paused = await original_pause_check(session, source)
        assert session.in_transaction(), "the pause SELECT must exercise a real transaction"
        pause_checked = True
        return paused

    async def record_started(source: str, trigger: str) -> UUID | None:
        run_id = await original_record_started(source, trigger)
        assert run_id is not None
        run_ids.append(run_id)
        return run_id

    async def fetch(_self: ClawhubAdapter, client: Any) -> AsyncIterator[RawItem]:
        assert pause_checked
        assert all(not session.in_transaction() for session in sessions), (
            "provider fetch inherited an open transaction from the pause check"
        )
        await asyncio.sleep(0)  # Yield as a slow provider would, without a real request.
        if failure == "provider":
            raise httpx.ReadTimeout("slow sitemap")
        if failure == "unexpected":
            raise RuntimeError("unexpected sitemap failure")
        yield RawItem(
            source_id=source_id,
            raw_body_bytes=b"",
            raw_body_hash="0" * 64,
            http_status=304,
            from_cache=True,
        )

    monkeypatch.setattr(get_settings(), "ingestion_source_blocklist", [])
    monkeypatch.setattr(session_module, "AsyncSessionLocal", tracked_session)
    monkeypatch.setattr(tasks, "is_source_paused", check_pause)
    monkeypatch.setattr(tasks, "record_run_started", record_started)
    monkeypatch.setattr(ClawhubAdapter, "list_items", fetch)
    monkeypatch.setattr(HttpClientFactory, "build", Mock(return_value=AsyncMock()))

    try:
        if failure == "unexpected":
            with pytest.raises(RuntimeError, match="unexpected sitemap failure"):
                await tasks.run_source_cycle("clawhub", trigger="manual")
        else:
            result = await tasks.run_source_cycle("clawhub", trigger="manual")
            if failure == "provider":
                assert result == {"skipped": "failed", "reason": "timeout"}
            else:
                assert result["items_seen"] == result["http_304_count"] == 1

        assert len(run_ids) == 1
        assert all(not session.in_transaction() for session in sessions)
        async with factory() as verification:
            run = await verification.get(IngestionRun, run_ids[0])
            assert run is not None
            assert run.status == ("failed" if failure else "succeeded")
            assert run.ended_at is not None
            assert run.trigger == "manual"
            assert (
                run.error_class
                == {
                    None: None,
                    "provider": "ReadTimeout",
                    "unexpected": "RuntimeError",
                }[failure]
            )
            events = (
                (
                    await verification.execute(
                        select(IngestionEvent).where(IngestionEvent.source_id == source_id)
                    )
                )
                .scalars()
                .all()
            )
            assert len(events) == (0 if failure else 1)
            if not failure:
                assert events[0].applied_at is not None
                assert run.items_seen == run.http_304_count == 1
    finally:
        async with factory() as cleanup:
            await cleanup.execute(
                delete(IngestionEvent).where(IngestionEvent.source_id == source_id)
            )
            await cleanup.execute(delete(IngestionRun).where(IngestionRun.id.in_(run_ids)))
            await cleanup.commit()
