"""90-day retention sweep for ingestion_runs (app.core.sweeps)."""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.sweeps import sweep_ingestion_runs


async def _insert(session: AsyncSession, *, source: str, age_days: int) -> None:
    await session.execute(
        text(
            "INSERT INTO ingestion_runs (source, trigger, status, started_at) "
            "VALUES (:s, 'scheduled', 'succeeded', now() - make_interval(days => :d))"
        ),
        {"s": source, "d": age_days},
    )


@pytest.mark.asyncio
async def test_sweep_deletes_only_old_runs(db_session: AsyncSession) -> None:
    await _insert(db_session, source="npm", age_days=120)
    await _insert(db_session, source="npm", age_days=91)
    await _insert(db_session, source="npm", age_days=10)  # recent → kept
    await db_session.commit()

    deleted = await sweep_ingestion_runs(db_session, days=90)
    assert deleted == 2

    remaining = (
        await db_session.execute(
            text(
                "SELECT count(*) FROM ingestion_runs "
                "WHERE source='npm' AND started_at > now() - make_interval(days => 90)"
            )
        )
    ).scalar_one()
    assert remaining >= 1
