"""Reconciliation drainer selection (the durable auto-scan coverage net).

`run_reconcile` selects public-github **repo-resolved** not-archived repos
(ANY quality tier — the high/medium gate was removed so every indexed,
scannable capability is covered, matching the merger's tier-less on-add scan
hook) that are unscanned / stale-version / stale-freshness, popularity-first,
deduped per repo URL, and defers a scan job for each (the deferrer is injected
so we assert selection without spawning real scans). Items with no `github_url`
(uploads / unresolved registry listings) remain excluded — nothing to fetch.
"""

from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.ingestion.tasks_scan import run_reconcile

from ._catalog_factory import make_item


class _Recorder:
    def __init__(self) -> None:
        self.urls: list[str] = []

    async def __call__(self, github_url: str) -> bool:
        self.urls.append(github_url)
        return True


def _current_versions() -> tuple[str, str]:
    s = get_settings()
    rubric = s.rubric_version or s.git_sha or "unknown"
    engine_v = s.engine_version or s.git_sha or "unknown"
    return rubric, engine_v


@pytest.mark.asyncio
async def test_selects_unscanned_excludes_fresh_and_offscope(db_session: AsyncSession) -> None:
    rubric, engine_v = _current_versions()
    now = dt.datetime.now(tz=dt.UTC)

    unscanned = make_item(popularity_score=90, last_scanned_at=None)
    fresh = make_item(
        popularity_score=80,
        last_scanned_at=now,
        last_checked_at=now,
        scanned_rubric_version=rubric,
        scanned_engine_version=engine_v,
    )
    archived = make_item(popularity_score=95, archived=True, last_scanned_at=None)
    # Low + empty tiers are now IN scope (gate widened) as long as they resolve a repo.
    low_quality = make_item(popularity_score=95, quality_tier="low", last_scanned_at=None)
    empty_quality = make_item(popularity_score=40, quality_tier="empty", last_scanned_at=None)
    upload = make_item(
        popularity_score=95, source_kind="upload", github_url=None, last_scanned_at=None
    )
    unlisted = make_item(popularity_score=95, visibility="unlisted", last_scanned_at=None)
    db_session.add_all([unscanned, fresh, archived, low_quality, empty_quality, upload, unlisted])
    await db_session.commit()

    rec = _Recorder()
    n = await run_reconcile(db_session, defer=rec)

    assert unscanned.github_url in rec.urls
    assert fresh.github_url not in rec.urls
    assert archived.github_url not in rec.urls
    # Widened gate: every repo-resolved tier is now covered (D: "each indexed skill scanned").
    assert low_quality.github_url in rec.urls
    assert empty_quality.github_url in rec.urls
    assert upload.github_url not in rec.urls  # github_url is None → unscannable, excluded
    assert unlisted.github_url not in rec.urls
    assert n == len(rec.urls)


@pytest.mark.asyncio
async def test_selects_stale_rubric_version(db_session: AsyncSession) -> None:
    """A scanned item whose stored rubric version != current is re-selected."""
    _, engine_v = _current_versions()
    now = dt.datetime.now(tz=dt.UTC)
    stale = make_item(
        popularity_score=70,
        last_scanned_at=now,
        last_checked_at=now,
        scanned_rubric_version="an-old-rubric-sha",
        scanned_engine_version=engine_v,
    )
    db_session.add(stale)
    await db_session.commit()

    rec = _Recorder()
    await run_reconcile(db_session, defer=rec)
    assert stale.github_url in rec.urls


@pytest.mark.asyncio
async def test_selects_stale_freshness(db_session: AsyncSession) -> None:
    """A current-version item not re-checked within SCAN_FRESHNESS_DAYS is selected."""
    rubric, engine_v = _current_versions()
    old = dt.datetime.now(tz=dt.UTC) - dt.timedelta(days=get_settings().scan_freshness_days + 5)
    stale = make_item(
        popularity_score=70,
        last_scanned_at=old,
        last_checked_at=old,
        scanned_rubric_version=rubric,
        scanned_engine_version=engine_v,
    )
    db_session.add(stale)
    await db_session.commit()

    rec = _Recorder()
    await run_reconcile(db_session, defer=rec)
    assert stale.github_url in rec.urls


@pytest.mark.asyncio
async def test_dedups_per_repo_url(db_session: AsyncSession) -> None:
    """Two capabilities sharing one repo URL produce a single scan defer."""
    url = "https://github.com/acme/shared-repo"
    cap_a = make_item(slug="acme--shared-repo--skill-a", github_url=url, last_scanned_at=None)
    cap_b = make_item(slug="acme--shared-repo--skill-b", github_url=url, last_scanned_at=None)
    db_session.add_all([cap_a, cap_b])
    await db_session.commit()

    rec = _Recorder()
    await run_reconcile(db_session, defer=rec)
    assert rec.urls.count(url) == 1


@pytest.mark.asyncio
async def test_popularity_first_within_batch(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The drainer enqueues the most popular stale repos first, bounded by the batch."""
    from app.ingestion import tasks_scan

    hi = make_item(popularity_score=99, last_scanned_at=None)
    lo = make_item(popularity_score=1, last_scanned_at=None)
    db_session.add_all([hi, lo])
    await db_session.commit()

    base = get_settings()
    monkeypatch.setattr(
        tasks_scan, "get_settings", lambda: base.model_copy(update={"scan_reconcile_batch": 1})
    )
    rec = _Recorder()
    await run_reconcile(db_session, defer=rec)
    assert rec.urls == [hi.github_url]  # only the most popular, batch=1
