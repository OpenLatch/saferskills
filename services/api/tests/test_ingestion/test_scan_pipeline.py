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
