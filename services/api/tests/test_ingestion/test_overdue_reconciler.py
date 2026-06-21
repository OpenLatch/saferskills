"""The overdue-cycle reconciler — the daily-cron ingestion safety net.

`reconcile_overdue_sources` re-defers any enabled cadenced source whose most-recent
cron tick has NOT been attempted (`max(ingestion_runs.started_at)` < the previous
tick). This is what makes daily-cron sources (`github_topics` + the aggregators)
actually run on a frequently-restarting worker, where Procrastinate's periodic
deferrer never backfills a stale daily tick. The deferrer is injected so the tests
assert SELECTION without enqueuing real Procrastinate jobs. Timestamps are anchored
to the computed previous tick (not wall-clock-relative) so the suite is stable at
any time of day.
"""

from __future__ import annotations

import datetime as dt
from types import SimpleNamespace
from typing import Any

import pytest
from croniter import croniter
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.ingestion import tasks
from app.ingestion.tasks import reconcile_overdue_sources
from app.models import CrawlerCursor, IngestionRun

_DAILY = "0 1 * * *"


def _prev_tick(now: dt.datetime) -> dt.datetime:
    """The most recent daily-cron fire ≤ now (what the reconciler compares against)."""
    return croniter(_DAILY, now).get_prev(dt.datetime)


class _Recorder:
    def __init__(self) -> None:
        self.sources: list[str] = []

    async def __call__(self, source: str) -> bool:
        self.sources.append(source)
        return True


def _cfg(*, kind: str = "api", cadence_cron: str | None = _DAILY, enabled: bool = True) -> Any:
    # The reconciler only reads .kind / .cadence_cron / .enabled off a config.
    return SimpleNamespace(kind=kind, cadence_cron=cadence_cron, enabled=enabled)


def _patch_sources(monkeypatch: pytest.MonkeyPatch, mapping: dict[str, Any]) -> None:
    monkeypatch.setattr(tasks, "load_source_configs", lambda: mapping)


async def _add_run(
    session: AsyncSession,
    source: str,
    started_at: dt.datetime,
    *,
    trigger: str = "scheduled",
) -> None:
    session.add(
        IngestionRun(source=source, trigger=trigger, status="succeeded", started_at=started_at)
    )
    await session.flush()


@pytest.mark.asyncio
async def test_never_attempted_is_overdue_recent_attempt_skipped(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    now = dt.datetime.now(tz=dt.UTC)
    prev = _prev_tick(now)
    _patch_sources(
        monkeypatch,
        {"daily_overdue": _cfg(), "daily_done": _cfg()},
    )
    # daily_done attempted AFTER the most recent tick → its cycle already ran.
    await _add_run(db_session, "daily_done", prev + dt.timedelta(minutes=1))
    await db_session.commit()

    rec = _Recorder()
    n = await reconcile_overdue_sources(db_session, defer=rec)

    assert "daily_overdue" in rec.sources  # never attempted → overdue
    assert "daily_done" not in rec.sources  # attempted after the tick → skip
    assert n == len(rec.sources) == 1


@pytest.mark.asyncio
async def test_attempt_before_tick_is_overdue(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A source last attempted BEFORE its most-recent tick (the missed-daily case)."""
    now = dt.datetime.now(tz=dt.UTC)
    prev = _prev_tick(now)
    _patch_sources(monkeypatch, {"daily_stale": _cfg()})
    # Last attempt was a minute before today's 01:00 tick → the tick was missed.
    await _add_run(db_session, "daily_stale", prev - dt.timedelta(minutes=1))
    await db_session.commit()

    rec = _Recorder()
    await reconcile_overdue_sources(db_session, defer=rec)
    assert rec.sources == ["daily_stale"]


@pytest.mark.asyncio
async def test_reconcile_run_record_stops_the_loop(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The keystone loop-stop: a reconcile-triggered run-record counts as an attempt.

    Once migration 0025 lets `record_run_started(source, "reconcile")` persist a row,
    `reconcile_overdue_sources` reads its `started_at` via `max(ingestion_runs.
    started_at)` and stops re-firing the source until the next real cron tick. Before
    the fix the reconcile INSERT was swallowed (CHECK violation) → no record → the
    source looked perpetually overdue and re-fired every 15 min. This proves a
    reconcile attempt at/after the current tick suppresses the next deferral."""
    now = dt.datetime.now(tz=dt.UTC)
    prev = _prev_tick(now)
    _patch_sources(monkeypatch, {"daily_reconciled": _cfg()})
    # The only attempt on record is a RECONCILE fire just after the latest tick.
    await _add_run(
        db_session, "daily_reconciled", prev + dt.timedelta(minutes=1), trigger="reconcile"
    )
    await db_session.commit()

    rec = _Recorder()
    n = await reconcile_overdue_sources(db_session, defer=rec)
    assert rec.sources == []  # the reconcile attempt is honored → no re-fire
    assert n == 0


@pytest.mark.asyncio
async def test_skips_disabled_webhook_and_noncron(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_sources(
        monkeypatch,
        {
            "off": _cfg(enabled=False),
            "hook": _cfg(kind="webhook", cadence_cron=None),
            "nocron": _cfg(cadence_cron=None),
        },
    )
    rec = _Recorder()
    n = await reconcile_overdue_sources(db_session, defer=rec)
    assert rec.sources == []
    assert n == 0


@pytest.mark.asyncio
async def test_skips_paused_source(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An operator-halted source is left alone even when overdue (no attempt yet)."""
    # github_topics has a seeded crawler_cursors row (migration 0011); pause it.
    await db_session.execute(
        update(CrawlerCursor).where(CrawlerCursor.source == "github_topics").values(status="paused")
    )
    _patch_sources(monkeypatch, {"github_topics": _cfg()})
    await db_session.commit()

    rec = _Recorder()
    await reconcile_overdue_sources(db_session, defer=rec)
    assert "github_topics" not in rec.sources


@pytest.mark.asyncio
async def test_invalid_cron_is_skipped(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_sources(monkeypatch, {"bad": _cfg(cadence_cron="not a cron")})
    rec = _Recorder()
    n = await reconcile_overdue_sources(db_session, defer=rec)
    assert rec.sources == []
    assert n == 0
