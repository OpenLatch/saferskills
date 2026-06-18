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

# ── _pick_manifest loose-file fallback (pure) ────────────────────────────────


def test_pick_manifest_falls_back_to_sole_loose_file() -> None:
    # No preferred manifest (skill.md/readme.md/manifest.json/package.json) — a
    # lone non-repo-wide text file surfaces its own bytes so the Source tab isn't
    # empty (an uploaded install.sh / server.json / .cursorrules).
    files = [("install.sh", b"#!/bin/sh\necho hi"), ("LICENSE", b"MIT")]
    result = persistence._pick_manifest(files, "hook")  # pyright: ignore[reportPrivateUsage]
    assert result is not None
    path, text = result
    assert path == "install.sh"
    assert "echo hi" in text


def test_pick_manifest_no_fallback_when_multiple_loose_files() -> None:
    files = [("a.sh", b"echo a"), ("b.sh", b"echo b")]
    assert persistence._pick_manifest(files, "hook") is None  # pyright: ignore[reportPrivateUsage]


def test_pick_manifest_prefers_skill_md_over_loose_fallback() -> None:
    files = [("SKILL.md", b"# real"), ("extra.cfg", b"x")]
    result = persistence._pick_manifest(files, "skill")  # pyright: ignore[reportPrivateUsage]
    assert result is not None
    assert result[0] == "SKILL.md"


def test_pick_manifest_strips_nul_from_utf16_readme() -> None:
    # A UTF-16 README (BOM + interleaved NUL bytes) must never reach the
    # `manifest_source` VARCHAR write — Postgres text columns reject U+0000 with
    # CharacterNotInRepertoireError. Decode is BOM-aware (stays readable) and any
    # residual NUL is stripped as the hard guarantee.
    body = "# Felix MCP (Smithery)\n\nA tool.".encode("utf-16")  # BOM + UTF-16-LE
    assert b"\x00" in body  # the byte that crashes the naive utf-8 decode path
    result = persistence._pick_manifest([("README.md", body)], "mcp_server")  # pyright: ignore[reportPrivateUsage]
    assert result is not None
    path, text = result
    assert path == "README.md"
    assert "\x00" not in text
    assert "Felix MCP" in text


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


@pytest.mark.asyncio
async def test_multifile_upload_run_report_carries_per_cap_extras(
    db_session: AsyncSession,
) -> None:
    """A multi-file upload fans into N capabilities, and the run report carries a
    per-capability manifest + download on each CapabilityRow (report tabs)."""
    from app.routers.scans import (
        _load_run_capabilities,  # pyright: ignore[reportPrivateUsage]
        _run_capability_extras,  # pyright: ignore[reportPrivateUsage]
    )
    from app.scan import engine
    from app.scan.report_builder import build_scan_run_report

    files = [
        ("prompt.md", b"# Prompt\nDo the thing safely."),
        ("install.sh", b"#!/bin/sh\necho hi"),
        ("server.json", b'{"name": "srv"}'),
    ]
    repo = engine.run_repo_scan_from_index(files, "a1b2c3d", source_kind="upload")
    assert repo.capability_count == 3  # anchorless upload fans out

    run = await persistence.persist_pending_scan_run(
        db_session,
        idempotency_key="u" * 64,
        github_url=None,
        rubric_version="a1b2c3d",
        engine_version="def5678",
        source="submission",
        source_kind="upload",
        content_hash_sha256="abc123def4567890",
        original_filename="3 files",
    )
    await persistence.persist_completed_scan_run(db_session, run, repo, full_files_index=files)
    await db_session.flush()

    caps = await _load_run_capabilities(db_session, run.id)
    extras, manifest, download = await _run_capability_extras(db_session, caps)
    report = build_scan_run_report(
        run, caps, manifest=manifest, download=download, capability_extras=extras
    )

    assert report.capability_count == 3
    assert report.source_kind == "upload"
    # Every capability row carries its own manifest (loose-file fallback) + zip +
    # its own per-file content hash (distinct per file → per-tab provenance SHA).
    for row in report.capabilities:
        assert row.manifest is not None, row.name
        assert row.download is not None, row.name
        assert row.download.scan_id == row.scan_id
        assert row.content_hash and len(row.content_hash) == 64, row.name
    hashes = {row.content_hash for row in report.capabilities}
    assert len(hashes) == 3  # each file's sha256 is distinct
    # The run-level manifest/download stay None for a multi-capability run (the
    # single-file rich path is the only consumer of the run-level pair).
    assert report.manifest is None
    assert report.download is None
