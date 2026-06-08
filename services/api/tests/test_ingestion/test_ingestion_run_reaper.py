"""Auto-reaper for orphaned `running` ingestion_runs rows (Fix 2).

A worker reload BETWEEN `record_run_started` and `record_run_finished` leaves the
row stuck `running` forever — which the eagle-eye health view reads as a permanent
`stuck` signal + inflated `running` count. `mark_stale_ingestion_runs` flips such
orphans to `failed`/`StaleRunReaped`; `recover_stale_ingestion_runs` is the boot +
periodic entry point; `ingestion_run_reaper` is the every-15-min Procrastinate task.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.ingestion import tasks
from app.models import IngestionRun


class _Ctx:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def __aenter__(self) -> AsyncSession:
        return self._session

    async def __aexit__(self, *args: object) -> None:
        pass


async def _insert_running(session: AsyncSession, *, source: str, age_minutes: int) -> None:
    await session.execute(
        text(
            "INSERT INTO ingestion_runs (source, trigger, status, started_at) "
            "VALUES (:s, 'scheduled', 'running', now() - make_interval(mins => :m))"
        ),
        {"s": source, "m": age_minutes},
    )


@pytest.mark.asyncio
async def test_mark_stale_ingestion_runs_flips_only_stale(db_session: AsyncSession) -> None:
    await _insert_running(db_session, source="mcp_registry", age_minutes=600)  # ~10h → stale
    await _insert_running(db_session, source="mcp_registry", age_minutes=1)  # fresh → kept
    await db_session.commit()

    cutoff = datetime.now(UTC) - timedelta(hours=1)
    reaped = await tasks.mark_stale_ingestion_runs(db_session, cutoff=cutoff)
    await db_session.commit()

    assert reaped == 1
    rows = (
        (
            await db_session.execute(
                select(IngestionRun).where(IngestionRun.source == "mcp_registry")
            )
        )
        .scalars()
        .all()
    )
    by_status = sorted((r.status, r.error_class) for r in rows)
    assert by_status == [("failed", "StaleRunReaped"), ("running", None)]
    failed = next(r for r in rows if r.status == "failed")
    assert failed.ended_at is not None
    assert failed.error_message == "reaped: stale running row"


@pytest.mark.asyncio
async def test_recover_stale_ingestion_runs_uses_grace_and_commits(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A row older than the 4h grace is reaped; a 1-minute-old one survives.
    await _insert_running(db_session, source="npm", age_minutes=60 * 5)  # 5h > 4h grace
    await _insert_running(db_session, source="npm", age_minutes=1)
    await db_session.commit()

    from app.db import session as session_module

    monkeypatch.setattr(session_module, "AsyncSessionLocal", lambda: _Ctx(db_session))

    reaped = await tasks.recover_stale_ingestion_runs()
    assert reaped == 1

    rows = (
        (await db_session.execute(select(IngestionRun).where(IngestionRun.source == "npm")))
        .scalars()
        .all()
    )
    assert sorted(r.status for r in rows) == ["failed", "running"]


@pytest.mark.asyncio
async def test_ingestion_run_reaper_task_delegates(monkeypatch: pytest.MonkeyPatch) -> None:
    # The periodic task is a thin wrapper over recover_stale_ingestion_runs and
    # reports the count.
    called = False

    async def _fake() -> int:
        nonlocal called
        called = True
        return 3

    monkeypatch.setattr(tasks, "recover_stale_ingestion_runs", _fake)
    result = await tasks.ingestion_run_reaper.func(timestamp=0)  # type: ignore[attr-defined]
    assert called is True
    assert result == {"reaped": 3}


def test_boot_hook_imports_reaper() -> None:
    # The boot hook in app/main.py imports this symbol right after recover_stale_scans;
    # a rename would break startup silently. Assert the symbol exists + is callable.
    assert callable(tasks.recover_stale_ingestion_runs)
