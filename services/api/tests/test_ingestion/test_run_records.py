"""Cycle-chokepoint run-record writes (independent-session pattern, trigger thread)."""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import IngestionRun


class _Ctx:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def __aenter__(self) -> AsyncSession:
        return self._session

    async def __aexit__(self, *args: object) -> None:
        pass


@pytest.mark.asyncio
async def test_record_started_then_finished(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.db import session as session_module
    from app.ingestion import tasks

    monkeypatch.setattr(session_module, "AsyncSessionLocal", lambda: _Ctx(db_session))

    run_id = await tasks.record_run_started("npm", "manual")
    assert run_id is not None

    started = (
        await db_session.execute(select(IngestionRun).where(IngestionRun.id == run_id))
    ).scalar_one()
    assert started.status == "running"
    assert started.trigger == "manual"

    await tasks.record_run_finished(
        run_id,
        status="succeeded",
        duration_ms=150,
        counters={"items_seen": 9, "items_added": 4, "items_updated": 1},
    )
    await db_session.refresh(started)
    assert started.status == "succeeded"
    assert started.duration_ms == 150
    assert started.items_added == 4


@pytest.mark.asyncio
async def test_record_finished_failure_stores_error(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.db import session as session_module
    from app.ingestion import tasks

    monkeypatch.setattr(session_module, "AsyncSessionLocal", lambda: _Ctx(db_session))

    run_id = await tasks.record_run_started("pypi", "force")
    assert run_id is not None
    await tasks.record_run_finished(
        run_id, status="failed", duration_ms=99, error=ValueError("boom")
    )
    row = (
        await db_session.execute(select(IngestionRun).where(IngestionRun.id == run_id))
    ).scalar_one()
    assert row.status == "failed"
    assert row.error_class == "ValueError"
    assert row.error_message == "boom"


@pytest.mark.asyncio
async def test_record_started_reconcile_trigger_persists(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression for the keystone staging bug: the overdue reconciler re-defers a
    missed cron tick with trigger='reconcile', but migration 0013's
    chk_ingestion_runs_trigger only allowed ('scheduled','manual','force'). Every
    reconcile run-record INSERT violated the CHECK, got swallowed (best-effort), and
    wrote NO row — so reconcile_overdue_sources never saw the attempt and re-fired the
    source every 15 min. Migration 0025 widens the CHECK; this asserts the row now
    persists with the reconcile trigger (fails on main: run_id is None)."""
    from app.db import session as session_module
    from app.ingestion import tasks

    monkeypatch.setattr(session_module, "AsyncSessionLocal", lambda: _Ctx(db_session))

    run_id = await tasks.record_run_started("github_topics", "reconcile")
    assert run_id is not None

    row = (
        await db_session.execute(select(IngestionRun).where(IngestionRun.id == run_id))
    ).scalar_one()
    assert row.status == "running"
    assert row.trigger == "reconcile"


@pytest.mark.asyncio
async def test_record_finished_noop_on_none() -> None:
    from app.ingestion import tasks

    # No session use, no raise — None run_id is a tolerated best-effort miss.
    await tasks.record_run_finished(None, status="succeeded", duration_ms=1)
