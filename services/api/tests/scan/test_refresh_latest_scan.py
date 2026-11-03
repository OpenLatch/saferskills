"""`catalog_items.latest_scan_*` stays correct at every scan writer."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.ingestion.tasks_latest_scan import backfill_latest_scan
from app.models.catalog_item import CatalogItem
from app.models.scan import Scan
from app.models.scan_run import ScanRun
from app.scan import persistence
from app.scan.engine import CapabilityResult, RepoScanResult, ScanResult
from app.scan.persistence import refresh_latest_scan
from app.services.repository_metadata import RepositoryMetadata

_NOW = datetime(2026, 11, 1, tzinfo=UTC)
_REPO_URL = "https://github.com/acme/latest"


@pytest.fixture(autouse=True)
def _no_network(monkeypatch: pytest.MonkeyPatch) -> None:  # pyright: ignore[reportUnusedFunction]
    async def _meta(_org: str, _repo: str) -> RepositoryMetadata:
        return RepositoryMetadata(stars=1, forks=0, license_spdx="MIT", latest_version="v1")

    monkeypatch.setattr(persistence, "get_repository_metadata", _meta)


async def _item(session: AsyncSession, *, slug: str | None = None) -> CatalogItem:
    token = uuid.uuid4().hex[:8]
    item = CatalogItem(
        kind="skill",
        slug=slug or f"acme--{token}",
        display_name=token,
        github_url=f"https://github.com/acme/{token}",
        github_org="acme",
        github_repo=token,
        default_branch="main",
        popularity_tier="indexed",
        popularity_score=1,
        agent_compatibility=[],
        sources=[],
    )
    session.add(item)
    await session.flush()
    return item


async def _scan(
    session: AsyncSession,
    item: CatalogItem,
    *,
    score: int,
    tier: str,
    age_days: int = 0,
    run_id: UUID | None = None,
) -> Scan:
    scan = Scan(
        catalog_item_id=item.id,
        scan_run_id=run_id,
        idempotency_key=uuid.uuid4().hex,
        github_url=item.github_url,
        ref_sha="0" * 40,
        aggregate_score=score,
        tier=tier,
        sub_scores={},
        score_breakdown={},
        rubric_version="r",
        engine_version="e",
        latency_ms=0,
        source="submission",
        scanned_at=_NOW - timedelta(days=age_days),
    )
    session.add(scan)
    await session.flush()
    return scan


async def _latest(session: AsyncSession, item_id: UUID) -> tuple[object, ...]:
    row = (
        await session.execute(
            select(
                CatalogItem.latest_scan_id,
                CatalogItem.latest_scan_score,
                CatalogItem.latest_scan_tier,
                CatalogItem.latest_scanned_at,
            )
            .where(CatalogItem.id == item_id)
            .execution_options(populate_existing=True)
        )
    ).one()
    return tuple(row)


def _result(score: int, tier: str) -> ScanResult:
    return ScanResult(
        findings=[],
        sub_scores={},
        score_breakdown={},
        aggregate_score=score,
        tier=tier,
        file_count=1,
        skipped_rules=[],
        skipped_files=[],
        ref_sha="a" * 40,
        latency_ms=0,
        files_index=[("SKILL.md", b"# hi")],
    )


def _repo(score: int, tier: str) -> RepoScanResult:
    return RepoScanResult(
        capabilities=[CapabilityResult("skill", "alpha", "skills/alpha", _result(score, tier))],
        repo_aggregate_score=score,
        repo_tier=tier,
        kind_tally={"skill": 1},
        capability_count=1,
        ref_sha="a" * 40,
        file_count=1,
        latency_ms=1,
        skipped_files=[],
    )


async def _run(session: AsyncSession, *, visibility: str = "public") -> ScanRun:
    return await persistence.persist_pending_scan_run(
        session,
        idempotency_key=uuid.uuid4().hex,
        github_url=_REPO_URL,
        rubric_version="r",
        engine_version="e",
        source="submission",
        visibility=visibility,
        share_token=uuid.uuid4().hex if visibility == "unlisted" else None,
    )


@pytest.mark.asyncio
async def test_picks_newest_completed_scan_and_ignores_a_newer_placeholder(
    db_session: AsyncSession,
) -> None:
    item = await _item(db_session)
    await _scan(db_session, item, score=40, tier="orange", age_days=3)
    newest = await _scan(db_session, item, score=90, tier="green", age_days=1)
    await _scan(db_session, item, score=0, tier="unscoped", age_days=0)

    assert await refresh_latest_scan(db_session, [item.id]) == 1

    assert await _latest(db_session, item.id) == (
        newest.id,
        90,
        "green",
        _NOW - timedelta(days=1),
    )


@pytest.mark.asyncio
async def test_item_with_only_a_placeholder_stays_null(db_session: AsyncSession) -> None:
    item = await _item(db_session)
    await _scan(db_session, item, score=0, tier="unscoped")

    assert await refresh_latest_scan(db_session, [item.id]) == 0

    assert await _latest(db_session, item.id) == (None, None, None, None)


@pytest.mark.asyncio
async def test_refresh_leaves_updated_at_alone_and_skips_unchanged_rows(
    db_session: AsyncSession,
) -> None:
    item = await _item(db_session)
    await _scan(db_session, item, score=90, tier="green")
    updated_at = (
        await db_session.execute(select(CatalogItem.updated_at).where(CatalogItem.id == item.id))
    ).scalar_one()

    assert await refresh_latest_scan(db_session, [item.id]) == 1
    assert await refresh_latest_scan(db_session, [item.id]) == 0

    after = (
        await db_session.execute(
            select(CatalogItem.updated_at)
            .where(CatalogItem.id == item.id)
            .execution_options(populate_existing=True)
        )
    ).scalar_one()
    assert after == updated_at


@pytest.mark.asyncio
async def test_single_scan_completion_updates_the_item(db_session: AsyncSession) -> None:
    item = await _item(db_session)
    placeholder = await _scan(db_session, item, score=0, tier="unscoped")

    await persistence.persist_completed_scan(db_session, placeholder, _result(77, "yellow"))

    assert (await _latest(db_session, item.id))[:3] == (placeholder.id, 77, "yellow")


@pytest.mark.asyncio
async def test_run_fan_out_updates_public_and_unlisted_shadow_items(
    db_session: AsyncSession,
) -> None:
    for visibility in ("public", "unlisted"):
        run = await _run(db_session, visibility=visibility)
        await persistence.persist_completed_scan_run(db_session, run, _repo(88, "green"))
        scan = (
            await db_session.execute(select(Scan).where(Scan.scan_run_id == run.id))
        ).scalar_one()
        assert (await _latest(db_session, scan.catalog_item_id))[:3] == (scan.id, 88, "green")


@pytest.mark.asyncio
async def test_promotion_merge_moves_the_latest_scan_to_the_canonical_item(
    db_session: AsyncSession,
) -> None:
    ref = persistence.parse_github_url(_REPO_URL)
    canonical = await _item(db_session, slug=persistence.capability_slug(ref, "skill", "alpha"))
    await _scan(db_session, canonical, score=20, tier="red", age_days=30)
    await refresh_latest_scan(db_session, [canonical.id])

    run = await _run(db_session, visibility="unlisted")
    await persistence.persist_completed_scan_run(db_session, run, _repo(95, "green"))
    moved = (await db_session.execute(select(Scan).where(Scan.scan_run_id == run.id))).scalar_one()

    _, items = await persistence.promote_run_to_public(db_session, run)

    assert items[0]["merged"] is True
    assert (await _latest(db_session, canonical.id))[:3] == (moved.id, 95, "green")


@pytest.mark.asyncio
async def test_deleting_a_run_falls_back_to_the_previous_scan_or_null(
    db_session: AsyncSession,
) -> None:
    run = await _run(db_session)
    with_history = await _item(db_session)
    previous = await _scan(db_session, with_history, score=50, tier="yellow", age_days=5)
    await _scan(db_session, with_history, score=90, tier="green", run_id=run.id)
    no_history = await _item(db_session)
    await _scan(db_session, no_history, score=90, tier="green", run_id=run.id)
    await refresh_latest_scan(db_session, [with_history.id, no_history.id])

    await persistence.delete_run_cascade(db_session, run.id, allow_public=True)

    assert (await _latest(db_session, with_history.id))[:3] == (previous.id, 50, "yellow")
    assert await _latest(db_session, no_history.id) == (None, None, None, None)


@pytest.mark.asyncio
async def test_resetting_a_failed_run_falls_back_to_the_previous_scan(
    db_session: AsyncSession,
) -> None:
    run = await _run(db_session)
    item = await _item(db_session)
    previous = await _scan(db_session, item, score=50, tier="yellow", age_days=5)
    await _scan(db_session, item, score=90, tier="green", run_id=run.id)
    await refresh_latest_scan(db_session, [item.id])

    await persistence.reset_failed_run_for_rerun(db_session, run)

    assert (await _latest(db_session, item.id))[:3] == (previous.id, 50, "yellow")


@pytest.mark.asyncio
async def test_backfill_fills_missing_rows_across_batches_and_is_idempotent(
    savepoint_session: AsyncSession,
) -> None:
    session = savepoint_session
    await session.execute(text("UPDATE catalog_items SET latest_scan_id = gen_random_uuid()"))
    items = [await _item(session) for _ in range(5)]
    scans = [
        await _scan(session, item, score=70 + i, tier="yellow") for i, item in enumerate(items)
    ]
    never_scanned = await _item(session)

    assert await backfill_latest_scan(session, batch=2, pause_s=0) == 5
    assert await backfill_latest_scan(session, batch=2, pause_s=0) == 0

    for item, scan in zip(items, scans, strict=True):
        assert (await _latest(session, item.id))[0] == scan.id
    assert await _latest(session, never_scanned.id) == (None, None, None, None)
