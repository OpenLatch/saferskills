"""Per-source crawler cursor read/write (crawler_cursors table).

The cursor is the resume marker (opaque per-source JSON) + the per-source health
fields the /sources dashboard reads. Always written AFTER the events tx.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CrawlerCursor


async def read_cursor(session: AsyncSession, source: str) -> dict[str, Any]:
    row = (
        await session.execute(select(CrawlerCursor).where(CrawlerCursor.source == source))
    ).scalar_one_or_none()
    return dict(row.cursor_value or {}) if row is not None else {}


async def write_cursor(
    session: AsyncSession, source: str, value: dict[str, Any], *, success: bool = True
) -> None:
    stmt = (
        update(CrawlerCursor)
        .where(CrawlerCursor.source == source)
        .values(
            cursor_value=value,
            updated_at=func.now(),
            last_attempted_cycle_at=func.now(),
            **(
                {"last_successful_cycle_at": func.now(), "consecutive_failure_count": 0}
                if success
                else {
                    "consecutive_failure_count": CrawlerCursor.consecutive_failure_count + 1,
                }
            ),
        )
    )
    await session.execute(stmt)


async def save_cursor_progress(session: AsyncSession, source: str, value: dict[str, Any]) -> None:
    """Persist ONLY the resume marker (cursor_value) mid-cycle — no health bookkeeping.

    Distinct from `write_cursor`: it does NOT touch `last_successful_cycle_at`,
    `last_attempted_cycle_at`, or `consecutive_failure_count`. Used to checkpoint an
    in-progress multi-page crawl (e.g. mcp_registry's full-feed sweep) so an aborted
    cycle (--reload / restart / stalled-retry) resumes from the last page instead of
    re-crawling from the epoch. A sweep is only marked successful by `write_cursor`
    once it completes.
    """
    await session.execute(
        update(CrawlerCursor)
        .where(CrawlerCursor.source == source)
        .values(cursor_value=value, updated_at=func.now())
    )


async def is_source_paused(session: AsyncSession, source: str) -> bool:
    row = (
        await session.execute(select(CrawlerCursor.status).where(CrawlerCursor.source == source))
    ).scalar_one_or_none()
    return row in {"paused", "blocked", "disabled"}
