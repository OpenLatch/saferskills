"""Source halt/status control (D-04-12 halt-source procedure).

Reads + writes the `crawler_cursors.status` lifecycle column (and its
status_reason / status_contact / status_changed_at companions). The cycle task
already no-ops when `is_source_paused()` is true (cursor.py); these helpers are
the write side the admin CLI drives (`saferskills-admin sources pause/unpause`)
and the read side `GET /api/v1/admin/sources` surfaces.

Status values (crawler_cursors CHECK, migration 0011): active | paused | blocked | disabled.
  paused   — temporary operator pause (aggregator requested a stop).
  blocked  — persistent technical block (e.g. Cloudflare tier-3 failure).
  disabled — permanent until manually re-enabled.
"""

from __future__ import annotations

import datetime as dt
from typing import Any, Literal, get_args

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CrawlerCursor

SourceStatus = Literal["active", "paused", "blocked", "disabled"]
_VALID_STATUS: frozenset[str] = frozenset(get_args(SourceStatus))


async def get_source_status(session: AsyncSession, source: str) -> dict[str, Any] | None:
    """Return the cursor's status snapshot for one source, or None if unknown."""
    cursor = (
        await session.execute(select(CrawlerCursor).where(CrawlerCursor.source == source))
    ).scalar_one_or_none()
    if cursor is None:
        return None
    return {
        "source": cursor.source,
        "status": cursor.status,
        "status_reason": cursor.status_reason,
        "status_contact": cursor.status_contact,
        "status_changed_at": cursor.status_changed_at,
        "last_successful_cycle_at": cursor.last_successful_cycle_at,
        "last_attempted_cycle_at": cursor.last_attempted_cycle_at,
        "consecutive_failure_count": cursor.consecutive_failure_count,
    }


async def set_source_status(
    session: AsyncSession,
    source: str,
    *,
    status: SourceStatus,
    reason: str | None = None,
    contact: str | None = None,
) -> dict[str, Any]:
    """Flip a source's status (+ reason/contact). Raises ValueError on an unknown
    status or unknown source. Caller commits."""
    if status not in _VALID_STATUS:
        raise ValueError(f"status must be one of {sorted(_VALID_STATUS)}, got {status!r}")
    result = await session.execute(
        text("""
            UPDATE crawler_cursors
            SET status = :status,
                status_reason = :reason,
                status_contact = :contact,
                status_changed_at = :now
            WHERE source = :source
            RETURNING source
        """),
        {
            "status": status,
            "reason": reason,
            "contact": contact,
            "now": dt.datetime.now(tz=dt.UTC),
            "source": source,
        },
    )
    if result.fetchone() is None:
        raise ValueError(f"unknown source {source!r}")
    snapshot = await get_source_status(session, source)
    assert snapshot is not None  # just updated it
    return snapshot
