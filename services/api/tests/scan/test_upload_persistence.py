"""DB integration: the upload/visibility persistence fork.

Covers the upload matrix: NULL-github scans insert, public-upload canonical item,
unlisted shadow rows (upload → upload_files, github → artifact_blobs), shadow
coexistence with a canonical row, the ordered `delete_run_cascade`, and
promote (bytes migration + re-slug + merge).
"""

from __future__ import annotations

import hashlib

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.artifact_blob import ArtifactBlob
from app.models.catalog_item import CatalogItem
from app.models.scan import Finding, Scan
from app.models.scan_run import ScanRun
from app.models.upload_file import UploadFile
from app.scan import persistence
from app.scan.engine import CapabilityResult, EngineFinding, RepoScanResult, ScanResult
from app.services.repository_metadata import RepositoryMetadata

_FILES = [("SKILL.md", b"---\nname: pdf\n---\n# PDF\n")]


def _scan_result(score: int = 90, findings: list[EngineFinding] | None = None) -> ScanResult:
    return ScanResult(
        findings=findings or [],
        sub_scores={
            k: score
            for k in ("security", "supply_chain", "maintenance", "transparency", "community")
        },
        score_breakdown={},
        aggregate_score=score,
        tier="green",
        file_count=1,
        skipped_rules=[],
        skipped_files=[],
        ref_sha="0" * 40,
        latency_ms=0,
        files_index=list(_FILES),
    )


def _repo_result(findings: list[EngineFinding] | None = None) -> RepoScanResult:
    return RepoScanResult(
        capabilities=[CapabilityResult("skill", "pdf", "", _scan_result(findings=findings))],
        repo_aggregate_score=90,
        repo_tier="green",
        kind_tally={"skill": 1},
        capability_count=1,
        ref_sha="0" * 40,
        file_count=1,
        latency_ms=0,
        skipped_files=[],
    )


def _content_hash() -> str:
    from app.scan.upload import upload_content_hash

    return upload_content_hash(_FILES)


async def _make_run(
    session: AsyncSession, *, source_kind: str, visibility: str, github_url: str | None = None
) -> ScanRun:
    ch = _content_hash()
    run = await persistence.persist_pending_scan_run(
        session,
        idempotency_key=hashlib.sha256(
            f"{visibility}{source_kind}{github_url}{ch}".encode()
        ).hexdigest(),
        github_url=github_url,
        rubric_version="abc1234",
        engine_version="def5678",
        source="submission",
        visibility=visibility,
        source_kind=source_kind,
        share_token=("t" + hashlib.sha256(ch.encode()).hexdigest()[:40])
        if visibility == "unlisted"
        else None,
        content_hash_sha256=ch,
    )
    return run


@pytest.fixture(autouse=True)
def _no_network(monkeypatch: pytest.MonkeyPatch) -> None:  # pyright: ignore[reportUnusedFunction]
    async def _meta(_org: str, _repo: str) -> RepositoryMetadata:
        return RepositoryMetadata(stars=1, forks=0, license_spdx="MIT", latest_version="v1")

    monkeypatch.setattr(persistence, "get_repository_metadata", _meta)


@pytest.mark.asyncio
async def test_public_upload_canonical_item_null_github_scan(db_session: AsyncSession) -> None:
    run = await _make_run(db_session, source_kind="upload", visibility="public")
    await persistence.persist_completed_scan_run(
        db_session, run, _repo_result(), full_files_index=_FILES
    )

    item = (
        (
            await db_session.execute(
                select(CatalogItem).where(
                    CatalogItem.owner_run_id.is_(None), CatalogItem.source_kind == "upload"
                )
            )
        )
        .scalars()
        .all()[-1]
    )
    assert item.visibility == "public"
    assert item.slug.startswith(f"upload--{_content_hash()[:8]}--skill-")
    assert item.github_url is None and item.github_org is None
    assert item.sources and item.sources[0]["registryId"] == "upload"

    scan = (await db_session.execute(select(Scan).where(Scan.scan_run_id == run.id))).scalar_one()
    assert scan.github_url is None and scan.ref_sha is None  # NULL insert
    assert scan.catalog_item_id == item.id


@pytest.mark.asyncio
async def test_unlisted_upload_shadow_and_upload_files(db_session: AsyncSession) -> None:
    run = await _make_run(db_session, source_kind="upload", visibility="unlisted")
    await persistence.persist_completed_scan_run(
        db_session, run, _repo_result(), full_files_index=_FILES
    )

    item = (
        await db_session.execute(select(CatalogItem).where(CatalogItem.owner_run_id == run.id))
    ).scalar_one()
    assert item.visibility == "unlisted"
    assert item.slug.startswith(f"unlisted--{str(run.id)[:8]}--skill-")

    n_files = (
        await db_session.execute(
            select(func.count(UploadFile.id)).where(UploadFile.scan_run_id == run.id)
        )
    ).scalar_one()
    assert n_files == 1


@pytest.mark.asyncio
async def test_unlisted_github_shadow_uses_blobs(db_session: AsyncSession) -> None:
    run = await _make_run(
        db_session,
        source_kind="github",
        visibility="unlisted",
        github_url="https://github.com/acme/x",
    )
    await persistence.persist_completed_scan_run(db_session, run, _repo_result())

    item = (
        await db_session.execute(select(CatalogItem).where(CatalogItem.owner_run_id == run.id))
    ).scalar_one()
    assert item.visibility == "unlisted" and item.github_url is None
    scan = (await db_session.execute(select(Scan).where(Scan.scan_run_id == run.id))).scalar_one()
    assert scan.github_url == "https://github.com/acme/x"  # github keeps real url
    # github bytes go to artifact_blobs (dedup), not upload_files.
    n_uploads = (
        await db_session.execute(
            select(func.count(UploadFile.id)).where(UploadFile.scan_run_id == run.id)
        )
    ).scalar_one()
    assert n_uploads == 0
    sha = hashlib.sha256(_FILES[0][1]).hexdigest()
    assert (
        await db_session.execute(select(ArtifactBlob).where(ArtifactBlob.sha256 == sha))
    ).scalar_one_or_none() is not None


@pytest.mark.asyncio
async def test_shadow_coexists_with_canonical(db_session: AsyncSession) -> None:
    url = "https://github.com/acme/coexist"
    pub = await _make_run(db_session, source_kind="github", visibility="public", github_url=url)
    await persistence.persist_completed_scan_run(db_session, pub, _repo_result())
    canonical = (
        await db_session.execute(select(CatalogItem).where(CatalogItem.github_url == url))
    ).scalar_one()
    assert canonical.visibility == "public" and canonical.owner_run_id is None

    unl = await _make_run(db_session, source_kind="github", visibility="unlisted", github_url=url)
    await persistence.persist_completed_scan_run(db_session, unl, _repo_result())

    await db_session.refresh(canonical)
    assert canonical.visibility == "public"  # never flipped
    shadow = (
        await db_session.execute(select(CatalogItem).where(CatalogItem.owner_run_id == unl.id))
    ).scalar_one()
    assert shadow.id != canonical.id and shadow.visibility == "unlisted"


@pytest.mark.asyncio
async def test_delete_run_cascade_ordered_and_refuses_public(db_session: AsyncSession) -> None:
    finding = EngineFinding(
        rule_id="SS-SKILL-INJECT-FENCED-RUN-01",
        severity="high",
        sub_score="security",
        penalty=10,
        status_at_scan="active",
        file_path="SKILL.md",
        line_start=1,
        line_end=2,
        matched_content_sha256="a" * 64,
        remediation_link="https://example.com/fix",
        rubric_version="abc1234",
    )
    run = await _make_run(db_session, source_kind="upload", visibility="unlisted")
    await persistence.persist_completed_scan_run(
        db_session, run, _repo_result([finding]), full_files_index=_FILES
    )
    scan_id = (
        await db_session.execute(select(Scan.id).where(Scan.scan_run_id == run.id))
    ).scalar_one()
    assert (
        await db_session.execute(
            select(func.count()).select_from(Finding).where(Finding.scan_id == scan_id)
        )
    ).scalar_one() == 1

    await persistence.delete_run_cascade(db_session, run.id)

    assert (
        await db_session.execute(
            select(func.count()).select_from(Finding).where(Finding.scan_id == scan_id)
        )
    ).scalar_one() == 0
    assert (
        await db_session.execute(
            select(func.count()).select_from(Scan).where(Scan.scan_run_id == run.id)
        )
    ).scalar_one() == 0
    assert (
        await db_session.execute(
            select(func.count()).select_from(UploadFile).where(UploadFile.scan_run_id == run.id)
        )
    ).scalar_one() == 0
    assert (
        await db_session.execute(
            select(func.count()).select_from(CatalogItem).where(CatalogItem.owner_run_id == run.id)
        )
    ).scalar_one() == 0
    assert await db_session.get(ScanRun, run.id) is None

    pub = await _make_run(db_session, source_kind="upload", visibility="public")
    await persistence.persist_completed_scan_run(
        db_session, pub, _repo_result(), full_files_index=_FILES
    )
    with pytest.raises(ValueError, match="public"):
        await persistence.delete_run_cascade(db_session, pub.id)


@pytest.mark.asyncio
async def test_promote_migrates_bytes_and_reslugs(db_session: AsyncSession) -> None:
    run = await _make_run(db_session, source_kind="upload", visibility="unlisted")
    await persistence.persist_completed_scan_run(
        db_session, run, _repo_result(), full_files_index=_FILES
    )

    promoted, items = await persistence.promote_run_to_public(db_session, run)
    assert promoted is True and len(items) == 1
    assert str(items[0]["slug"]).startswith("upload--") and items[0]["merged"] is False

    await db_session.refresh(run)
    assert run.visibility == "public" and run.expires_at is None
    # upload_files migrated → artifact_blobs; per-run rows gone.
    assert (
        await db_session.execute(
            select(func.count()).select_from(UploadFile).where(UploadFile.scan_run_id == run.id)
        )
    ).scalar_one() == 0
    sha = hashlib.sha256(_FILES[0][1]).hexdigest()
    assert (
        await db_session.execute(select(ArtifactBlob).where(ArtifactBlob.sha256 == sha))
    ).scalar_one_or_none() is not None

    # Idempotent re-promote.
    again, _ = await persistence.promote_run_to_public(db_session, run)
    assert again is False


@pytest.mark.asyncio
async def test_resolver_reads_unlisted_bytes_from_upload_files(db_session: AsyncSession) -> None:
    from app.services.artifact_bytes import resolve_snapshot

    run = await _make_run(db_session, source_kind="upload", visibility="unlisted")
    await persistence.persist_completed_scan_run(
        db_session, run, _repo_result(), full_files_index=_FILES
    )
    scan = (await db_session.execute(select(Scan).where(Scan.scan_run_id == run.id))).scalar_one()

    snapshot = await resolve_snapshot(db_session, scan)
    assert snapshot["SKILL.md"] == _FILES[0][1]  # bytes resolved from upload_files


@pytest.mark.asyncio
async def test_two_unlisted_runs_identical_bytes_no_collision(db_session: AsyncSession) -> None:
    a = await _make_run(db_session, source_kind="upload", visibility="unlisted")
    await persistence.persist_completed_scan_run(
        db_session, a, _repo_result(), full_files_index=_FILES
    )
    b = await _make_run(db_session, source_kind="upload", visibility="unlisted")
    await persistence.persist_completed_scan_run(
        db_session, b, _repo_result(), full_files_index=_FILES
    )
    # Distinct runs, distinct shadow items, distinct scan rows — no UNIQUE clash.
    items = (
        (
            await db_session.execute(
                select(CatalogItem.id).where(CatalogItem.owner_run_id.in_([a.id, b.id]))
            )
        )
        .scalars()
        .all()
    )
    assert len(set(items)) == 2
