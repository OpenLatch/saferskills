"""Route integration: upload submit + capability URLs + visibility.

Uses the SAVEPOINT `db_client`; the fire-and-forget scan worker is monkeypatched
to a no-op so we assert the request/response + DB-write contract, not the async
engine plumbing (that is covered directly in `tests/scan/test_upload_persistence`).
"""

from __future__ import annotations

import hashlib
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.session import get_session
from app.main import app
from app.models.catalog_item import CatalogItem
from app.models.scan import Scan
from app.models.scan_run import ScanRun
from app.queue import scan_runner


@pytest.fixture(autouse=True)
def _no_worker(monkeypatch: pytest.MonkeyPatch) -> None:  # pyright: ignore[reportUnusedFunction]
    async def _noop(*_a: object, **_k: object) -> None:
        return None

    monkeypatch.setattr(scan_runner, "scan_run_upload", _noop)
    monkeypatch.setattr(scan_runner, "scan_run_repo", _noop)


def _files(name: str = "SKILL.md", body: bytes = b"---\nname: t\n---\n# t\n"):
    return {"file": (name, body, "text/markdown")}


@pytest.mark.asyncio
async def test_upload_single_md_returns_202(db_client: AsyncClient) -> None:
    r = await db_client.post("/api/v1/scans/upload", files=_files(), data={"visibility": "public"})
    assert r.status_code == 202
    body = r.json()
    assert body["source_kind"] == "upload"
    assert body["visibility"] == "public"
    assert body["share_url"] is None


def _multi(*entries: tuple[str, bytes]) -> list[tuple[str, tuple[str, bytes, str]]]:
    """httpx multi-part: several parts all named `file` (the multi-file batch)."""
    return [("file", (name, body, "text/plain")) for name, body in entries]


@pytest.mark.asyncio
async def test_upload_multi_file_returns_202(db_client: AsyncClient) -> None:
    files = _multi(("SKILL.md", b"---\nname: t\n---\n# t\n"), ("run.py", b"print(1)\n"))
    r = await db_client.post("/api/v1/scans/upload", files=files, data={"visibility": "public"})
    assert r.status_code == 202
    assert r.json()["source_kind"] == "upload"


@pytest.mark.asyncio
async def test_upload_total_cap_across_parts(db_client: AsyncClient) -> None:
    """The 10 MiB cap is cumulative — two parts each under the cap but summing
    over it → 413 (byte-accounting spans ALL parts)."""
    cap = get_settings().upload_max_bytes
    half = b"x" * (cap // 2 + 1024)
    files = _multi(("a.txt", half), ("b.txt", half))
    r = await db_client.post("/api/v1/scans/upload", files=files)
    assert r.status_code == 413 and r.json()["detail"]["error"] == "upload_too_large"


@pytest.mark.asyncio
async def test_upload_zip_in_batch_rejected(db_client: AsyncClient) -> None:
    files = _multi(("SKILL.md", b"# a"), ("inner.zip", b"PK\x03\x04rest"))
    r = await db_client.post("/api/v1/scans/upload", files=files)
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert detail["error"] == "archive_rejected" and detail["reason"] == "nesting"


@pytest.mark.asyncio
async def test_upload_dup_basename_in_batch_rejected(db_client: AsyncClient) -> None:
    files = _multi(("README.md", b"a"), ("readme.md", b"b"))
    r = await db_client.post("/api/v1/scans/upload", files=files)
    assert r.status_code == 422 and r.json()["detail"]["reason"] == "dup_path"


@pytest.mark.asyncio
async def test_upload_single_zip_returns_202(db_client: AsyncClient) -> None:
    import io
    import zipfile

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("SKILL.md", b"---\nname: z\n---\n# z\n")
    r = await db_client.post(
        "/api/v1/scans/upload",
        files={"file": ("bundle.zip", buf.getvalue(), "application/zip")},
        data={"visibility": "public"},
    )
    assert r.status_code == 202 and r.json()["source_kind"] == "upload"


@pytest.mark.asyncio
async def test_upload_rejections(db_client: AsyncClient) -> None:
    too_big = b"x" * (get_settings().upload_max_bytes + 1)
    r = await db_client.post("/api/v1/scans/upload", files=_files("a.md", too_big))
    assert r.status_code == 413 and r.json()["detail"]["error"] == "upload_too_large"

    r = await db_client.post("/api/v1/scans/upload", files=_files("a.exe", b"x"))
    assert r.status_code == 415 and r.json()["detail"]["error"] == "unsupported_type"


@pytest.mark.asyncio
async def test_public_caches_unlisted_does_not(db_client: AsyncClient) -> None:
    a = (
        await db_client.post("/api/v1/scans/upload", files=_files(), data={"visibility": "public"})
    ).json()
    b = (
        await db_client.post("/api/v1/scans/upload", files=_files(), data={"visibility": "public"})
    ).json()
    assert a["id"] == b["id"]  # public caches on content hash

    u1 = (
        await db_client.post(
            "/api/v1/scans/upload", files=_files(), data={"visibility": "unlisted"}
        )
    ).json()
    u2 = (
        await db_client.post(
            "/api/v1/scans/upload", files=_files(), data={"visibility": "unlisted"}
        )
    ).json()
    assert u1["id"] != u2["id"]  # never cached
    assert u1["share_url"] and u2["share_url"] and u1["share_url"] != u2["share_url"]


@pytest.mark.asyncio
async def test_public_failed_run_is_rerun_not_reserved(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Regression: a `failed` public upload must NOT be re-served from the
    idempotency cache. Re-submitting the same bytes re-runs it IN PLACE (reuses the
    id so its report URL keeps working, resets to pending) instead of returning the
    stale failure forever — the bug where the asyncpg-pool incident left runs
    cached `failed`, so re-uploading the same file kept showing "scan didn't
    complete" even after the pool was fixed."""
    first = (
        await db_client.post("/api/v1/scans/upload", files=_files(), data={"visibility": "public"})
    ).json()
    run_id = first["id"]

    # Simulate the scan having failed (e.g. the NOTIFY pool was dead at scan time).
    run = await db_session.get(ScanRun, UUID(run_id))
    assert run is not None
    run.status = "failed"
    await db_session.flush()

    # Re-submit the SAME bytes — must re-run in place, not re-serve the failure.
    again = (
        await db_client.post("/api/v1/scans/upload", files=_files(), data={"visibility": "public"})
    ).json()
    assert again["id"] == run_id  # reused id → the existing report URL keeps working
    assert again["status"] == "pending"  # re-running, not a stale cache hit

    await db_session.refresh(run)
    assert run.status == "pending"  # reset for the re-run, no longer failed


async def _seed_unlisted_run(session: AsyncSession, *, expired: bool = False) -> ScanRun:
    token = (
        "tok-"
        + hashlib.sha256(
            str(datetime.now(UTC).timestamp() + (1 if expired else 0)).encode()
        ).hexdigest()[:40]
    )
    run = ScanRun(
        idempotency_key=hashlib.sha256(token.encode()).hexdigest(),
        github_url=None,
        ref_sha=None,
        repo_aggregate_score=80,
        repo_tier="green",
        kind_tally={"skill": 1},
        capability_count=1,
        rubric_version="abc1234",
        engine_version="def5678",
        source="submission",
        latency_ms=10,
        file_count=1,
        status="completed",
        visibility="unlisted",
        source_kind="upload",
        share_token=token,
        original_filename="SKILL.md",
        content_hash_sha256="a" * 64,
        expires_at=datetime.now(UTC) + timedelta(days=-1 if expired else 90),
    )
    session.add(run)
    await session.flush()
    item = CatalogItem(
        kind="skill",
        slug=f"unlisted--{str(run.id)[:8]}--skill-t",
        display_name="t",
        popularity_tier="on_demand",
        agent_compatibility=["claude-code"],
        visibility="unlisted",
        source_kind="upload",
        owner_run_id=run.id,
        sources=[],
    )
    session.add(item)
    await session.flush()
    session.add(
        Scan(
            catalog_item_id=item.id,
            scan_run_id=run.id,
            idempotency_key=hashlib.sha256(("scan" + token).encode()).hexdigest(),
            github_url=None,
            ref_sha=None,
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
            rubric_version="abc1234",
            engine_version="def5678",
            latency_ms=10,
            source="submission",
        )
    )
    await session.flush()
    return run


@pytest.mark.asyncio
async def test_capability_url_view_headers_and_404(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    run = await _seed_unlisted_run(db_session)
    r = await db_client.get(f"/api/v1/scans/r/{run.share_token}")
    assert r.status_code == 200
    assert r.headers["x-robots-tag"] == "noindex, nofollow"
    assert r.headers["referrer-policy"] == "no-referrer"
    assert r.headers["cache-control"] == "private, no-store"
    body = r.json()
    assert body["visibility"] == "unlisted"
    assert body["share_url"].endswith(f"/scans/r/{run.share_token}")

    # Invalid + expired → generic 404 (no oracle).
    assert (await db_client.get("/api/v1/scans/r/does-not-exist")).status_code == 404
    expired = await _seed_unlisted_run(db_session, expired=True)
    assert (await db_client.get(f"/api/v1/scans/r/{expired.share_token}")).status_code == 404


@pytest.mark.asyncio
async def test_promote_then_delete(db_client: AsyncClient, db_session: AsyncSession) -> None:
    run = await _seed_unlisted_run(db_session)
    r = await db_client.post(f"/api/v1/scans/r/{run.share_token}/promote")
    assert r.status_code == 200
    body = r.json()
    assert body["promoted"] is True and body["visibility"] == "public"
    assert len(body["items"]) == 1 and body["items"][0]["slug"].startswith("upload--")

    # After promote, GET the token → 307 to the run report.
    r = await db_client.get(f"/api/v1/scans/r/{run.share_token}", follow_redirects=False)
    assert r.status_code == 307
    assert r.headers["location"].endswith(f"/scans/runs/{run.id}")

    # A second unlisted run can be deleted; token then 404s.
    run2 = await _seed_unlisted_run(db_session)
    assert (await db_client.delete(f"/api/v1/scans/r/{run2.share_token}")).status_code == 204
    assert (await db_client.get(f"/api/v1/scans/r/{run2.share_token}")).status_code == 404


@pytest.mark.asyncio
async def test_unlisted_excluded_from_feed_and_no_share_url(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    run = await _seed_unlisted_run(db_session)
    feed = (await db_client.get("/api/v1/scans?limit=100")).json()
    ids = {row["id"] for row in feed["data"]}
    assert str(run.id) not in ids
    # share_url / token never in any list payload.
    raw = (await db_client.get("/api/v1/scans?limit=100")).text
    assert "share_url" not in raw and str(run.share_token) not in raw


@pytest.mark.asyncio
async def test_unlisted_item_404_on_public_surface(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    run = await _seed_unlisted_run(db_session)
    from sqlalchemy import select

    slug = (
        await db_session.execute(select(CatalogItem.slug).where(CatalogItem.owner_run_id == run.id))
    ).scalar_one()
    assert (await db_client.get(f"/api/v1/items/{slug}")).status_code == 404


async def _attach_bytes(session: AsyncSession, run: ScanRun, body: bytes = b"# t\nhello\n") -> None:
    """Give the run's single scan a stored snapshot in `upload_files` so the
    download + manifest/source resolver have something to serve."""
    from sqlalchemy import select

    from app.models.upload_file import UploadFile

    scan = (await session.execute(select(Scan).where(Scan.scan_run_id == run.id))).scalar_one()
    scan.file_hashes = {"SKILL.md": None}  # null sha → resolved from upload_files
    scan.manifest_path = "SKILL.md"
    scan.manifest_source = body.decode()
    session.add(
        UploadFile(
            scan_run_id=run.id,
            path="SKILL.md",
            content=body,
            byte_size=len(body),
            is_binary=False,
        )
    )
    await session.flush()


@pytest.mark.asyncio
async def test_unlisted_download_zip(db_client: AsyncClient, db_session: AsyncSession) -> None:
    run = await _seed_unlisted_run(db_session)
    await _attach_bytes(db_session, run)
    r = await db_client.get(f"/api/v1/scans/r/{run.share_token}/download")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/zip")
    # Anti-leakage parity with the view route + a real zip payload.
    assert r.headers["x-robots-tag"] == "noindex, nofollow"
    assert r.headers["cache-control"] == "private, no-store"
    assert r.content[:2] == b"PK"
    # Bad / unknown token → generic 404 (no oracle), never a hint.
    assert (await db_client.get("/api/v1/scans/r/nope/download")).status_code == 404


@pytest.mark.asyncio
async def test_run_report_carries_manifest_and_download(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    run = await _seed_unlisted_run(db_session)
    await _attach_bytes(db_session, run, b"# my-skill\nbody\n")
    body = (await db_client.get(f"/api/v1/scans/r/{run.share_token}")).json()
    # Single-capability upload run → rich report gets the source viewer + .zip pointer.
    assert body["manifest"]["path"] == "SKILL.md"
    assert "my-skill" in body["manifest"]["content"]
    assert body["download"]["byte_size"] > 0


@pytest.mark.asyncio
async def test_private_lookup_rate_limit(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A routable (non-loopback) IP is capped on /scans/r/{token}; loopback isn't."""
    monkeypatch.setattr(get_settings(), "private_lookup_daily_limit", 1)
    run = await _seed_unlisted_run(db_session)

    async def _override() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_session] = _override
    try:
        transport = ASGITransport(app=app, client=("203.0.113.9", 5555))
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            url = f"/api/v1/scans/r/{run.share_token}"
            first = await ac.get(url)
            second = await ac.get(url)
        assert first.status_code == 200
        assert second.status_code == 429
    finally:
        app.dependency_overrides.pop(get_session, None)
