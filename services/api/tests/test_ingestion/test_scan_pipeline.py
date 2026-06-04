"""Durable scan pipeline — change-gate decision, merger hook, stale-run recovery."""

from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ingestion.framework.merger import MergeEngine
from app.ingestion.tasks_scan import decide_scan_action
from app.models.scan_run import ScanRun
from app.queue.scan_runner import mark_stale_runs_failed

from .conftest import make_normalized

# ── change-gate decision (pure) ────────────────────────────────────────────


def test_decide_skip_when_unchanged_and_current() -> None:
    assert (
        decide_scan_action(ref_unchanged=True, versions_current=True, has_prior_scan=True) == "skip"
    )


def test_decide_reeval_on_version_bump_with_prior_scan() -> None:
    assert (
        decide_scan_action(ref_unchanged=True, versions_current=False, has_prior_scan=True)
        == "reeval"
    )


def test_decide_full_scan_on_content_change() -> None:
    assert (
        decide_scan_action(ref_unchanged=False, versions_current=True, has_prior_scan=True)
        == "scan"
    )


def test_decide_full_scan_when_never_scanned() -> None:
    # Unchanged ref but no prior scan (e.g. fetch-state exists, never scored) → scan.
    assert (
        decide_scan_action(ref_unchanged=True, versions_current=False, has_prior_scan=False)
        == "scan"
    )


# ── permanent fetch failure does not dead-letter ───────────────────────────


class _Ctx:
    """Yield the test session from a patched AsyncSessionLocal (commit kept — the
    SAVEPOINT fixture owns teardown rollback)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def __aenter__(self) -> AsyncSession:
        return self._session

    async def __aexit__(self, *args: object) -> None:
        pass


@pytest.mark.asyncio
async def test_full_scan_records_failed_on_permanent_fetch_error(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An oversized tarball (FetchError) marks the run failed + returns 'error'
    instead of bubbling out to a Procrastinate retry → dead-letter."""
    from app.db import session as session_module
    from app.ingestion import tasks_scan
    from app.scan import engine as engine_module
    from app.scan.fetch import FetchError, ResolvedRef

    monkeypatch.setattr(session_module, "AsyncSessionLocal", lambda: _Ctx(db_session))

    async def _raise_oversize(github_url: str, rubric_version: str) -> object:
        raise FetchError("tarball exceeded 26214400 bytes; aborting (anti-DOS cap)")

    monkeypatch.setattr(engine_module, "run_repo_scan", _raise_oversize)

    url = "https://github.com/acme/oversized-repo"
    resolved = ResolvedRef(
        org="acme",
        repo="oversized-repo",
        default_branch="main",
        ref_sha="a" * 40,
        etag=None,
        last_modified=None,
        not_modified=False,
    )

    action = await tasks_scan._full_scan(  # pyright: ignore[reportPrivateUsage]
        url, "rub1", "eng1", resolved, reason="reconcile"
    )
    assert action == "error"

    run = (await db_session.execute(select(ScanRun).where(ScanRun.github_url == url))).scalar_one()
    assert run.status == "failed"


# ── merger on-ingest scan hook ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_merger_defers_scan_on_add(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A new public-github capability enqueues a durable scan of its repo URL."""
    from app.ingestion import tasks_scan

    deferred: list[str] = []

    async def _record(github_url: str, reason: str = "reconcile") -> bool:
        deferred.append(github_url)
        return True

    monkeypatch.setattr(tasks_scan, "defer_scan_job", _record)

    n = make_normalized(github_org="acme", github_repo="brand-new", kind="skill")
    outcome = await MergeEngine(db_session).upsert(n, raw_hash="a" * 64, source="github_topics")
    await db_session.commit()

    assert outcome == "added"
    assert n.github_url in deferred


@pytest.mark.asyncio
async def test_merger_defers_scan_on_content_change(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A re-crawl with a changed content hash enqueues a re-scan."""
    from app.ingestion import tasks_scan

    deferred: list[str] = []

    async def _record(github_url: str, reason: str = "reconcile") -> bool:
        deferred.append(github_url)
        return True

    monkeypatch.setattr(tasks_scan, "defer_scan_job", _record)

    n = make_normalized(github_org="acme", github_repo="drifty", kind="skill")
    await MergeEngine(db_session).upsert(n, raw_hash="1" * 64, source="github_topics")
    await db_session.commit()
    deferred.clear()

    # Second crawl, DIFFERENT content hash → drift → re-scan deferred.
    await MergeEngine(db_session).upsert(n, raw_hash="2" * 64, source="github_topics")
    await db_session.commit()
    assert n.github_url in deferred


@pytest.mark.asyncio
async def test_merger_no_scan_for_fuzzy_no_coordinate(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A row with no GitHub coordinate goes to the fuzzy queue — never a scan defer."""
    from app.ingestion import tasks_scan

    deferred: list[str] = []

    async def _record(github_url: str, reason: str = "reconcile") -> bool:
        deferred.append(github_url)
        return True

    monkeypatch.setattr(tasks_scan, "defer_scan_job", _record)

    n = make_normalized(github_org=None, github_repo=None, display_name="orphan-skill")
    outcome = await MergeEngine(db_session).upsert(n, raw_hash="3" * 64, source="npm")
    await db_session.commit()

    assert outcome in {"added", "added_with_merge_candidate"}
    assert deferred == []


# ── stale interactive-run recovery ─────────────────────────────────────────


def _pending_run(github_url: str, *, created_at: dt.datetime) -> ScanRun:
    return ScanRun(
        idempotency_key=f"k-{created_at.timestamp()}-{github_url}"[:64],
        github_url=github_url,
        ref_sha=None,
        repo_aggregate_score=0,
        repo_tier="unscoped",
        kind_tally={},
        capability_count=0,
        rubric_version="abc1234",
        engine_version="def5678",
        source="submission",
        latency_ms=0,
        file_count=0,
        status="running",
        visibility="public",
        source_kind="github",
        created_at=created_at,
    )


@pytest.mark.asyncio
async def test_mark_stale_runs_failed(db_session: AsyncSession) -> None:
    """Runs created before the cutoff flip to failed; recent ones are untouched."""
    now = dt.datetime.now(tz=dt.UTC)
    old = _pending_run("https://github.com/acme/orphan", created_at=now - dt.timedelta(hours=2))
    recent = _pending_run("https://github.com/acme/live", created_at=now)
    db_session.add_all([old, recent])
    await db_session.flush()

    cutoff = now - dt.timedelta(minutes=15)
    n = await mark_stale_runs_failed(db_session, cutoff=cutoff)
    await db_session.flush()

    assert n == 1
    refreshed = {
        r.github_url: r.status for r in (await db_session.execute(select(ScanRun))).scalars().all()
    }
    assert refreshed["https://github.com/acme/orphan"] == "failed"
    assert refreshed["https://github.com/acme/live"] == "running"


# ── defer_scan_job dedup pre-check (queueing_lock retry collision) ──────────


@pytest.mark.asyncio
async def test_defer_scan_job_skips_while_running(monkeypatch: pytest.MonkeyPatch) -> None:
    """Regression: the pre-check only looked at `todo`, so a fresh enqueue was
    allowed while a job was `doing`. When that running job later failed and
    Procrastinate retried it (todo again), it collided with the sibling todo on
    `procrastinate_jobs_queueing_lock_idx_v1` → duplicate-key ERROR in the DB log.
    A `doing` job must now suppress the enqueue."""
    from app.ingestion import tasks_scan

    class _Job:
        def __init__(self, status: str) -> None:
            self.status = status

    # Faithfully model the DB: one job is `doing`. Honour the `status` kwarg the
    # way Postgres would — so the OLD pre-check (`status="todo"`) sees nothing and
    # wrongly enqueues, while the NEW unfiltered pre-check sees the `doing` job.
    async def _list_doing(**kwargs: object) -> list[_Job]:
        jobs = [_Job("doing")]
        status = kwargs.get("status")
        if status is not None:
            jobs = [j for j in jobs if j.status == status]
        return jobs

    deferred: list[str] = []

    async def _defer(**kwargs: object) -> None:
        deferred.append(str(kwargs.get("github_url")))

    monkeypatch.setattr(tasks_scan.procrastinate_app.job_manager, "list_jobs_async", _list_doing)

    # If the pre-check wrongly proceeds, this configure(...).defer_async would run.
    def _configure(**_: object) -> object:
        return type("C", (), {"defer_async": staticmethod(_defer)})()

    monkeypatch.setattr(tasks_scan.scan_capability_repo, "configure", _configure)

    result = await tasks_scan.defer_scan_job("https://github.com/acme/running-repo")
    assert result is False
    assert deferred == []  # no enqueue while a job is running


@pytest.mark.asyncio
async def test_defer_scan_job_enqueues_when_idle(monkeypatch: pytest.MonkeyPatch) -> None:
    """The flip side: no active (todo/doing) job → the enqueue proceeds."""
    from app.ingestion import tasks_scan

    async def _list_none(**kwargs: object) -> list[object]:
        return []

    deferred: list[str] = []

    async def _defer(**kwargs: object) -> None:
        deferred.append(str(kwargs.get("github_url")))

    monkeypatch.setattr(tasks_scan.procrastinate_app.job_manager, "list_jobs_async", _list_none)

    def _configure(**_: object) -> object:
        return type("C", (), {"defer_async": staticmethod(_defer)})()

    monkeypatch.setattr(tasks_scan.scan_capability_repo, "configure", _configure)

    result = await tasks_scan.defer_scan_job("https://github.com/acme/idle-repo")
    assert result is True
    assert deferred == ["https://github.com/acme/idle-repo"]
