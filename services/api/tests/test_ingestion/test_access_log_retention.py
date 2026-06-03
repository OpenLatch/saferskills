"""access_log_retention — 30-day row sweep (privacy.md retention)."""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.ingestion.tasks_retention import sweep_access_log


async def _insert_row(session: AsyncSession, *, age_days: int) -> None:
    await session.execute(
        text(
            "INSERT INTO access_log (ts, action, ip) "
            "VALUES (now() - make_interval(days => :d), 'item_view', NULL)"
        ),
        {"d": age_days},
    )


@pytest.mark.asyncio
async def test_sweep_deletes_only_old_rows(db_session: AsyncSession) -> None:
    await _insert_row(db_session, age_days=31)
    await _insert_row(db_session, age_days=40)
    await _insert_row(db_session, age_days=5)  # recent → kept
    await db_session.commit()

    deleted = await sweep_access_log(db_session, days=30)
    assert deleted == 2

    remaining = (
        await db_session.execute(
            text("SELECT count(*) FROM access_log WHERE ts > now() - make_interval(days => 30)")
        )
    ).scalar_one()
    assert remaining >= 1
