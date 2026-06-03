"""Tests for app.ingestion.framework.cursor — read/write/is_source_paused."""

from __future__ import annotations

import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.ingestion.framework.cursor import is_source_paused, read_cursor, write_cursor
from app.models import CrawlerCursor

# Migration 0011 seeds one row per source. We use an existing source name
# that the migration seeds, so we don't need to INSERT.
_SOURCE = "github_topics"


@pytest.mark.asyncio
async def test_read_cursor_returns_empty_dict_for_missing_source(
    db_session: AsyncSession,
) -> None:
    result = await read_cursor(db_session, "no_such_source_xyz")
    assert result == {}


@pytest.mark.asyncio
async def test_read_cursor_returns_value_after_write(db_session: AsyncSession) -> None:
    await write_cursor(db_session, _SOURCE, {"seq": 42, "last_name": "abc"}, success=True)
    result = await read_cursor(db_session, _SOURCE)
    assert result.get("seq") == 42
    assert result.get("last_name") == "abc"


@pytest.mark.asyncio
async def test_write_cursor_success_resets_failure_count(db_session: AsyncSession) -> None:
    # First set consecutive_failure_count to >0
    await db_session.execute(
        update(CrawlerCursor)
        .where(CrawlerCursor.source == _SOURCE)
        .values(consecutive_failure_count=3)
    )
    await write_cursor(db_session, _SOURCE, {"seq": 1}, success=True)

    row = (
        await db_session.execute(select(CrawlerCursor).where(CrawlerCursor.source == _SOURCE))
    ).scalar_one()
    assert row.consecutive_failure_count == 0


@pytest.mark.asyncio
async def test_write_cursor_failure_increments_failure_count(
    db_session: AsyncSession,
) -> None:
    # Set failure count to 1, then call with success=False
    await db_session.execute(
        update(CrawlerCursor)
        .where(CrawlerCursor.source == _SOURCE)
        .values(consecutive_failure_count=1)
    )
    await write_cursor(db_session, _SOURCE, {"seq": 0}, success=False)

    row = (
        await db_session.execute(select(CrawlerCursor).where(CrawlerCursor.source == _SOURCE))
    ).scalar_one()
    assert row.consecutive_failure_count == 2


@pytest.mark.asyncio
async def test_is_source_paused_returns_false_for_active(db_session: AsyncSession) -> None:
    # Ensure source is active
    await db_session.execute(
        update(CrawlerCursor).where(CrawlerCursor.source == _SOURCE).values(status="active")
    )
    result = await is_source_paused(db_session, _SOURCE)
    assert result is False


@pytest.mark.asyncio
async def test_is_source_paused_returns_true_for_paused(db_session: AsyncSession) -> None:
    await db_session.execute(
        update(CrawlerCursor).where(CrawlerCursor.source == _SOURCE).values(status="paused")
    )
    result = await is_source_paused(db_session, _SOURCE)
    assert result is True


@pytest.mark.asyncio
async def test_is_source_paused_returns_true_for_blocked(db_session: AsyncSession) -> None:
    await db_session.execute(
        update(CrawlerCursor).where(CrawlerCursor.source == _SOURCE).values(status="blocked")
    )
    result = await is_source_paused(db_session, _SOURCE)
    assert result is True


@pytest.mark.asyncio
async def test_is_source_paused_returns_true_for_disabled(db_session: AsyncSession) -> None:
    await db_session.execute(
        update(CrawlerCursor).where(CrawlerCursor.source == _SOURCE).values(status="disabled")
    )
    result = await is_source_paused(db_session, _SOURCE)
    assert result is True


@pytest.mark.asyncio
async def test_is_source_paused_returns_false_for_missing_source(
    db_session: AsyncSession,
) -> None:
    result = await is_source_paused(db_session, "no_such_source_xyz")
    assert result is False
