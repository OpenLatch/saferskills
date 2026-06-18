"""Source halt/status helper."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.ingestion.framework.halt import get_source_status, set_source_status


@pytest.mark.asyncio
async def test_pause_then_unpause(db_session: AsyncSession) -> None:
    # crawler_cursors are seeded (14 sources) by migration 0011.
    paused = await set_source_status(
        db_session, "npm", status="paused", reason="operator-request", contact="abuse@npm"
    )
    assert paused["status"] == "paused"
    assert paused["status_reason"] == "operator-request"
    assert paused["status_contact"] == "abuse@npm"

    snap = await get_source_status(db_session, "npm")
    assert snap is not None and snap["status"] == "paused"

    active = await set_source_status(db_session, "npm", status="active")
    assert active["status"] == "active"


@pytest.mark.asyncio
async def test_unknown_source_raises(db_session: AsyncSession) -> None:
    with pytest.raises(ValueError, match="unknown source"):
        await set_source_status(db_session, "not_a_real_source", status="paused")


@pytest.mark.asyncio
async def test_invalid_status_raises(db_session: AsyncSession) -> None:
    with pytest.raises(ValueError, match="status must be"):
        await set_source_status(db_session, "npm", status="bogus")  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_get_unknown_source_returns_none(db_session: AsyncSession) -> None:
    assert await get_source_status(db_session, "nope") is None
