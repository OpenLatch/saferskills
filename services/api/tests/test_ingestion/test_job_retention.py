"""`procrastinate_job_retention` against Procrastinate's real schema, triggers and FKs."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any
from uuid import uuid4

import pytest
import pytest_asyncio
from procrastinate.schema import SchemaManager
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.ingestion.tasks_retention import sweep_succeeded_jobs


@pytest_asyncio.fixture
async def savepoint_session(db_engine: Any) -> AsyncIterator[AsyncSession]:
    """The sweep commits per batch, so its commits must stay inside a rollback."""
    async with db_engine.connect() as conn:
        outer = await conn.begin()
        session = AsyncSession(
            bind=conn, join_transaction_mode="create_savepoint", expire_on_commit=False
        )
        try:
            yield session
        finally:
            await session.close()
            await outer.rollback()


@pytest.mark.asyncio
async def test_sweep_deletes_only_old_succeeded_jobs_across_batches(
    savepoint_session: AsyncSession,
) -> None:
    session = savepoint_session
    schema = f"retention_{uuid4().hex}"
    await session.execute(text(f'CREATE SCHEMA "{schema}"'))
    await session.execute(text(f'SET LOCAL search_path TO "{schema}", public'))
    raw = await (await session.connection()).get_raw_connection()
    driver: Any = raw.driver_connection
    await driver.execute(SchemaManager.get_schema())

    async def job(final_status: str, *, age_days: int) -> int:
        job_id: int = await driver.fetchval(
            "INSERT INTO procrastinate_jobs (queue_name, task_name) "
            "VALUES ('periodic', 't') RETURNING id"
        )
        await driver.execute("UPDATE procrastinate_jobs SET status = 'doing' WHERE id = $1", job_id)
        await driver.execute(
            f"UPDATE procrastinate_jobs SET status = '{final_status}' WHERE id = $1", job_id
        )
        await driver.execute(
            "UPDATE procrastinate_events SET at = now() - make_interval(days => $1) "
            "WHERE job_id = $2",
            age_days,
            job_id,
        )
        return job_id

    old_succeeded = [await job("succeeded", age_days=8) for _ in range(5)]
    recent_succeeded = await job("succeeded", age_days=6)
    old_failed = await job("failed", age_days=30)
    await driver.execute(
        "INSERT INTO procrastinate_periodic_defers (task_name, defer_timestamp, job_id) "
        "VALUES ('t', 1, $1)",
        old_succeeded[0],
    )

    # A batch smaller than the backlog, so the sweep has to loop.
    deleted = await sweep_succeeded_jobs(session, days=7, batch=2, pause_s=0)

    assert deleted == 5
    survivors = {row["id"] for row in await driver.fetch("SELECT id FROM procrastinate_jobs")}
    assert survivors == {recent_succeeded, old_failed}
    events = await driver.fetchval(
        "SELECT count(*) FROM procrastinate_events WHERE job_id = ANY($1::bigint[])",
        old_succeeded,
    )
    assert events == 0
    assert await driver.fetchval("SELECT job_id FROM procrastinate_periodic_defers") is None
