"""DB integration: persist_completed_scan_run fans out N items + N scans + 1 run."""

from __future__ import annotations

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.catalog_item import CatalogItem
from app.models.scan import Finding, Scan
from app.scan import persistence
from app.scan.engine import (
    CapabilityResult,
    EngineFinding,
    RepoScanResult,
    ScanResult,
)
from app.services.repository_metadata import RepositoryMetadata


def _scan_result(score: int, tier: str, findings: list[EngineFinding] | None = None) -> ScanResult:
    return ScanResult(
        findings=findings or [],
        sub_scores={
            "security": score,
            "supply_chain": score,
            "maintenance": score,
            "transparency": score,
            "community": score,
        },
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


def _repo_result() -> RepoScanResult:
    caps = [
        CapabilityResult("skill", "alpha", "skills/alpha", _scan_result(90, "green")),
        CapabilityResult("hook", "pre-commit", "hooks/pre-commit.json", _scan_result(78, "yellow")),
        CapabilityResult("mcp_server", "gh", "servers/gh", _scan_result(88, "green")),
    ]
    return RepoScanResult(
        capabilities=caps,
        repo_aggregate_score=85,
        repo_tier="green",
        kind_tally={"skill": 1, "hook": 1, "mcp_server": 1},
        capability_count=3,
        ref_sha="a" * 40,
        file_count=12,
        latency_ms=4200,
        skipped_files=[],
    )


@pytest.mark.asyncio
async def test_persist_run_creates_n_items_n_scans_one_run(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def _no_network(_org: str, _repo: str) -> RepositoryMetadata:
        return RepositoryMetadata(stars=10, forks=2, license_spdx="MIT", latest_version="v1")

    monkeypatch.setattr(persistence, "get_repository_metadata", _no_network)

    run = await persistence.persist_pending_scan_run(
        db_session,
        idempotency_key="k" * 64,
        github_url="https://github.com/acme/kit",
        rubric_version="a1b2c3d",
        engine_version="def5678",
        source="submission",
    )
    await persistence.persist_completed_scan_run(db_session, run, _repo_result())
    await db_session.flush()

    # 3 catalog items, distinct per-capability slugs, all sharing the repo URL.
    items = (
        (
            await db_session.execute(
                select(CatalogItem).where(CatalogItem.github_url == "https://github.com/acme/kit")
            )
        )
        .scalars()
        .all()
    )
    assert len(items) == 3
    slugs = {i.slug for i in items}
    assert "acme--kit--skill-alpha" in slugs
    assert "acme--kit--hook-pre-commit" in slugs
    assert "acme--kit--mcp-server-gh" in slugs
    assert {i.kind for i in items} == {"skill", "hook", "mcp_server"}

    # 3 scans, all linked to the run + carrying their component_path.
    scans = (
        (await db_session.execute(select(Scan).where(Scan.scan_run_id == run.id))).scalars().all()
    )
    assert len(scans) == 3
    assert all(s.component_path for s in scans)

    # The run rollup is written.
    assert run.repo_aggregate_score == 85
    assert run.capability_count == 3
    assert run.kind_tally == {"skill": 1, "hook": 1, "mcp_server": 1}
    assert run.status == "completed"


@pytest.mark.asyncio
async def test_rescan_run_updates_in_place_no_duplicates(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def _no_network(_org: str, _repo: str) -> RepositoryMetadata:
        return RepositoryMetadata()

    monkeypatch.setattr(persistence, "get_repository_metadata", _no_network)

    run = await persistence.persist_pending_scan_run(
        db_session,
        idempotency_key="m" * 64,
        github_url="https://github.com/acme/kit2",
        rubric_version="a1b2c3d",
        engine_version="def5678",
        source="submission",
    )
    await persistence.persist_completed_scan_run(db_session, run, _repo_result())
    await persistence.persist_completed_scan_run(db_session, run, _repo_result())
    await db_session.flush()

    # Re-running the same run does not duplicate scans or findings.
    scan_count = (
        await db_session.execute(select(func.count(Scan.id)).where(Scan.scan_run_id == run.id))
    ).scalar_one()
    assert scan_count == 3
    items = (
        await db_session.execute(
            select(func.count(CatalogItem.id)).where(
                CatalogItem.github_url == "https://github.com/acme/kit2"
            )
        )
    ).scalar_one()
    assert items == 3
    findings = (await db_session.execute(select(func.count(Finding.id)))).scalar_one()
    assert findings == 0  # clean repo result → no findings, no accumulation
