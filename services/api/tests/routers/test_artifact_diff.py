"""Tests for stored-snapshot capture, the diff service, and the
`/items/{slug}/diff` + `/items/{slug}/download` endpoints.

DB-backed (runs in `test-be` against Postgres) plus pure-function unit tests for
`diff_snapshots`. Covers happy paths and the adversarial surface: foreign
scan_id, missing snapshot, malformed id, per-IP rate cap, snapshot size cap,
binary/oversize flagging, and total-bytes truncation.
"""

from __future__ import annotations

import hashlib
import io
import uuid
import zipfile
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.main import app
from app.models.artifact_blob import ArtifactBlob
from app.models.catalog_item import CatalogItem
from app.models.scan import Scan
from app.services import artifact_diff
from app.services.artifact_diff import diff_snapshots

# ── unit: diff_snapshots ─────────────────────────────────────────────────────


def test_diff_modified_file_yields_add_del_ctx() -> None:
    old = {"a.txt": b"line1\nline2\n"}
    new = {"a.txt": b"line1\nline2 changed\n"}
    result = diff_snapshots(old, new)

    assert result.truncated is False
    assert len(result.files) == 1
    f = result.files[0]
    assert f.path == "a.txt"
    assert f.status == "modified"
    types = [ln.type for h in f.hunks for ln in h.lines]
    assert "add" in types and "del" in types and "ctx" in types


def test_diff_added_removed_and_identical() -> None:
    old = {"keep.txt": b"same\n", "gone.txt": b"x\n"}
    new = {"keep.txt": b"same\n", "new.txt": b"y\n"}
    by_path = {f.path: f.status for f in diff_snapshots(old, new).files}

    assert by_path == {"gone.txt": "removed", "new.txt": "added"}  # keep.txt skipped


def test_diff_binary_is_flagged_without_body() -> None:
    # `None` = known-but-not-stored (binary/oversize sentinel).
    old = {"img.png": None, "keep.txt": b"a\n"}
    new = {"keep.txt": b"a\n"}
    files = diff_snapshots(old, new).files

    assert len(files) == 1
    assert files[0].status == "binary"
    assert files[0].hunks == []
    assert files[0].note


def test_diff_binary_unchanged_on_both_sides_skipped() -> None:
    result = diff_snapshots({"img.png": None}, {"img.png": None})
    assert result.files == []


def test_diff_oversize_file_collapses_to_summary(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(artifact_diff, "_MAX_LINES_PER_FILE", 2)
    old = {"big.txt": b"a\nb\nc\n"}
    new = {"big.txt": b"a\nb\nc\nd\ne\n"}
    f = diff_snapshots(old, new).files[0]

    assert f.hunks == []
    assert f.note and "collapsed" in f.note


def test_diff_total_bytes_cap_truncates(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(artifact_diff, "_MAX_TOTAL_DIFF_BYTES", 10)
    old = {f"f{i}.txt": b"old line here\n" for i in range(5)}
    new = {f"f{i}.txt": b"new line here\n" for i in range(5)}
    result = diff_snapshots(old, new)

    assert result.truncated is True
    assert len(result.files) < 5  # stopped early


# ── unit: snapshot capture / dedup ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_capture_snapshot_dedups_and_flags_binary(db_session: AsyncSession) -> None:
    from app.scan.persistence import _capture_snapshot  # pyright: ignore[reportPrivateUsage]

    files_index = [
        ("a.txt", b"hello\n"),
        ("b.txt", b"hello\n"),  # identical bytes → same sha (dedup)
        ("img", b"PNG\x00\x01binary"),  # NUL → binary sentinel
    ]
    file_map = await _capture_snapshot(db_session, files_index)

    assert file_map["a.txt"] == file_map["b.txt"]  # deduped to one sha
    assert file_map["img"] is None  # known-but-not-stored
    sha = file_map["a.txt"]
    assert sha == hashlib.sha256(b"hello\n").hexdigest()

    stored = (
        (await db_session.execute(select(ArtifactBlob).where(ArtifactBlob.sha256 == sha)))
        .scalars()
        .all()
    )
    assert len(stored) == 1  # single blob row for the shared content
    assert stored[0].content == b"hello\n"
    assert stored[0].is_binary is False


# ── fixtures: an item with two snapshotted scans ─────────────────────────────


async def _store(session: AsyncSession, files: dict[str, bytes]) -> dict[str, str | None]:
    """Insert blobs + return the {path: sha} file_hashes map."""
    file_map: dict[str, str | None] = {}
    for path, content in files.items():
        sha = hashlib.sha256(content).hexdigest()
        if not (
            await session.execute(select(ArtifactBlob).where(ArtifactBlob.sha256 == sha))
        ).scalar_one_or_none():
            session.add(
                ArtifactBlob(sha256=sha, content=content, byte_size=len(content), is_binary=False)
            )
        file_map[path] = sha
    await session.flush()
    return file_map


async def _seed_two_scans(
    session: AsyncSession,
) -> tuple[CatalogItem, Scan, Scan]:
    suffix = uuid.uuid4().hex[:8]
    item = CatalogItem(
        kind="skill",
        slug=f"diff--demo-{suffix}",
        display_name="Diff Demo",
        github_url=f"https://github.com/diff/demo-{suffix}",
        github_org="diff",
        github_repo=f"demo-{suffix}",
        default_branch="main",
        popularity_tier="indexed",
        popularity_score=10,
        sources=[],
    )
    session.add(item)
    await session.flush()

    now = datetime.now(tz=UTC)
    older_map = await _store(session, {"SKILL.md": b"# demo\nversion 1\n"})
    newer_map = await _store(session, {"SKILL.md": b"# demo\nversion 2\n"})

    def _scan(ref: str, when: datetime, fh: dict[str, str | None]) -> Scan:
        return Scan(
            catalog_item_id=item.id,
            idempotency_key=uuid.uuid4().hex,
            github_url=item.github_url,
            ref_sha=ref * 40,
            aggregate_score=80,
            tier="green",
            sub_scores={
                "security": 80,
                "supply_chain": 80,
                "maintenance": 80,
                "transparency": 80,
                "community": 80,
            },
            score_breakdown={},
            file_hashes=fh,
            rubric_version="abc1234",
            engine_version="def5678",
            latency_ms=100,
            source="submission",
            scanned_at=when,
        )

    older = _scan("a", now - timedelta(days=2), older_map)
    newer = _scan("b", now, newer_map)
    session.add_all([older, newer])
    await session.flush()
    return item, older, newer


# ── endpoint: /diff ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_diff_endpoint_happy(db_client: AsyncClient, db_session: AsyncSession) -> None:
    item, older, newer = await _seed_two_scans(db_session)
    resp = await db_client.get(
        f"/api/v1/items/{item.slug}/diff", params={"to": str(newer.id), "from": str(older.id)}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["from_scan_id"] == str(older.id)
    assert body["to_scan_id"] == str(newer.id)
    assert any(f["path"] == "SKILL.md" and f["status"] == "modified" for f in body["files"])


@pytest.mark.asyncio
async def test_diff_endpoint_defaults_from_to_prior_scan(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    item, older, newer = await _seed_two_scans(db_session)
    resp = await db_client.get(f"/api/v1/items/{item.slug}/diff", params={"to": str(newer.id)})
    assert resp.status_code == 200
    assert resp.json()["from_scan_id"] == str(older.id)


@pytest.mark.asyncio
async def test_diff_foreign_scan_id_404(db_client: AsyncClient, db_session: AsyncSession) -> None:
    item, _older, newer = await _seed_two_scans(db_session)
    other_item, _o2, other_newer = await _seed_two_scans(db_session)
    # A scan from another item must never diff under this slug.
    resp = await db_client.get(
        f"/api/v1/items/{item.slug}/diff",
        params={"to": str(newer.id), "from": str(other_newer.id)},
    )
    assert resp.status_code == 404
    assert other_item.slug  # silence unused


@pytest.mark.asyncio
async def test_diff_missing_snapshot_404(db_client: AsyncClient, db_session: AsyncSession) -> None:
    item, _older, newer = await _seed_two_scans(db_session)
    # A pre-storage scan (file_hashes NULL) under the same item.
    bare = Scan(
        catalog_item_id=item.id,
        idempotency_key=uuid.uuid4().hex,
        github_url=item.github_url,
        ref_sha="c" * 40,
        aggregate_score=70,
        tier="yellow",
        sub_scores={
            "security": 70,
            "supply_chain": 70,
            "maintenance": 70,
            "transparency": 70,
            "community": 70,
        },
        score_breakdown={},
        rubric_version="abc1234",
        engine_version="def5678",
        latency_ms=100,
        source="submission",
        scanned_at=datetime.now(tz=UTC) + timedelta(days=1),
    )
    db_session.add(bare)
    await db_session.flush()
    resp = await db_client.get(
        f"/api/v1/items/{item.slug}/diff", params={"to": str(bare.id), "from": str(newer.id)}
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_diff_invalid_scan_id_400(db_client: AsyncClient, db_session: AsyncSession) -> None:
    item, _older, _newer = await _seed_two_scans(db_session)
    resp = await db_client.get(f"/api/v1/items/{item.slug}/diff", params={"to": "not-a-uuid"})
    assert resp.status_code == 400


# ── endpoint: /download ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_download_returns_zip(db_client: AsyncClient, db_session: AsyncSession) -> None:
    item, _older, newer = await _seed_two_scans(db_session)
    resp = await db_client.get(
        f"/api/v1/items/{item.slug}/download", params={"scan": str(newer.id)}
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/zip"
    assert "attachment" in resp.headers["content-disposition"]
    assert "immutable" in resp.headers["cache-control"]
    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        assert "SKILL.md" in zf.namelist()
        assert zf.read("SKILL.md") == b"# demo\nversion 2\n"


@pytest.mark.asyncio
async def test_download_no_snapshot_404(db_client: AsyncClient, db_session: AsyncSession) -> None:
    suffix = uuid.uuid4().hex[:8]
    item = CatalogItem(
        kind="skill",
        slug=f"nodl--demo-{suffix}",
        display_name="No Download",
        github_url=f"https://github.com/nodl/demo-{suffix}",
        github_org="nodl",
        github_repo=f"demo-{suffix}",
        default_branch="main",
        popularity_tier="indexed",
        popularity_score=1,
        sources=[],
    )
    db_session.add(item)
    await db_session.flush()
    resp = await db_client.get(f"/api/v1/items/{item.slug}/download")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_download_size_cap_413(
    db_client: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.routers import items as items_router

    monkeypatch.setattr(items_router, "_MAX_ZIP_BYTES", 4)  # tiny — any real snapshot busts it
    item, _older, newer = await _seed_two_scans(db_session)
    resp = await db_client.get(
        f"/api/v1/items/{item.slug}/download", params={"scan": str(newer.id)}
    )
    assert resp.status_code == 413


@pytest.mark.asyncio
async def test_download_rate_cap_for_public_ip(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A routable (non-loopback) IP is capped; the loopback test client is not."""
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "artifact_download_daily_limit", 1)
    item, _older, newer = await _seed_two_scans(db_session)

    async def _override() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_session] = _override
    try:
        transport = ASGITransport(app=app, client=("203.0.113.9", 5555))
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            url = f"/api/v1/items/{item.slug}/download"
            first = await ac.get(url, params={"scan": str(newer.id)})
            second = await ac.get(url, params={"scan": str(newer.id)})
        assert first.status_code == 200
        assert second.status_code == 429
    finally:
        app.dependency_overrides.pop(get_session, None)
