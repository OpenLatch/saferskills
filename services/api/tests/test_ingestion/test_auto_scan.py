"""auto-scan trigger selection (D-04-14/15) with an injected enqueue."""
# pyright: reportPrivateUsage=false

from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.ingestion.tasks_auto_scan import _SELECT_DEEP, _SELECT_LITE, run_trigger

from ._catalog_factory import make_item


class _Recorder:
    def __init__(self) -> None:
        self.calls: list[dict[str, str]] = []

    async def __call__(self, *, catalog_item_id: str, github_url: str, depth: str) -> None:
        self.calls.append({"id": catalog_item_id, "url": github_url, "depth": depth})


@pytest.mark.asyncio
async def test_deep_selects_top500_missing_recent_deep(db_session: AsyncSession) -> None:
    due = make_item(popularity_rank_tier="top500", popularity_score=90, last_deep_scan_at=None)
    fresh = make_item(
        popularity_rank_tier="top500",
        popularity_score=80,
        last_deep_scan_at=dt.datetime.now(tz=dt.UTC),  # scanned just now → skip
    )
    long_tail = make_item(popularity_rank_tier="long_tail", popularity_score=70)
    db_session.add_all([due, fresh, long_tail])
    await db_session.commit()

    rec = _Recorder()
    n = await run_trigger(
        db_session, select_stmt=_SELECT_DEEP, limit=100, depth="deep", enqueue=rec
    )
    selected_ids = {c["id"] for c in rec.calls}
    assert str(due.id) in selected_ids
    assert str(fresh.id) not in selected_ids
    assert str(long_tail.id) not in selected_ids
    assert all(c["depth"] == "deep" for c in rec.calls)
    assert n == len(rec.calls)


@pytest.mark.asyncio
async def test_lite_excludes_uploads_and_unlisted(db_session: AsyncSession) -> None:
    ok = make_item(popularity_rank_tier="top5k", popularity_score=50, last_lite_scan_at=None)
    upload = make_item(popularity_rank_tier="top5k", source_kind="upload", github_url=None)
    unlisted = make_item(popularity_rank_tier="top5k", visibility="unlisted")
    db_session.add_all([ok, upload, unlisted])
    await db_session.commit()

    rec = _Recorder()
    await run_trigger(db_session, select_stmt=_SELECT_LITE, limit=200, depth="lite", enqueue=rec)
    ids = {c["id"] for c in rec.calls}
    assert str(ok.id) in ids
    assert str(upload.id) not in ids
    assert str(unlisted.id) not in ids


@pytest.mark.asyncio
async def test_enqueue_scan_rejects_bad_depth() -> None:
    from app.queue.scan_runner import enqueue_scan

    with pytest.raises(ValueError, match=r"depth must"):
        await enqueue_scan(catalog_item_id="x", github_url="https://github.com/a/b", depth="bogus")


@pytest.mark.asyncio
async def test_lite_debounces_brand_new(db_session: AsyncSession) -> None:
    brand_new = make_item(
        popularity_rank_tier="top5k",
        created_at=dt.datetime.now(tz=dt.UTC),  # < 1h old → debounced out
    )
    db_session.add(brand_new)
    await db_session.commit()
    rec = _Recorder()
    await run_trigger(db_session, select_stmt=_SELECT_LITE, limit=200, depth="lite", enqueue=rec)
    assert str(brand_new.id) not in {c["id"] for c in rec.calls}
