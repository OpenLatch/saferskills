"""Route integration: the CLI Proof-of-Work gate replaces Turnstile.

- `GET /scans/cli-challenge` → 200 when the secret is set, 503 when unset.
- A non-loopback CLI caller with a solved `X-SaferSkills-CLI-PoW` header and NO
  Turnstile token passes both submit endpoints — and increments the
  `cli_scan_submit` bucket, not `scan_submit`.
- A forged PoW header → 403 `pow_failed`.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.session import get_session
from app.main import app
from app.queue import scan_runner
from tests.pow_helpers import solve_pow

_DIFFICULTY = 8


@pytest.fixture(autouse=True)
def _configure(monkeypatch: pytest.MonkeyPatch) -> None:  # pyright: ignore[reportUnusedFunction]
    # Both gates configured: Turnstile active (so the non-PoW path would 403) AND
    # the PoW secret set — proving the PoW path is what lets the request through.
    monkeypatch.setattr(get_settings(), "turnstile_secret_key", "1x000...AA")
    monkeypatch.setattr(get_settings(), "saferskills_cli_pow_secret", "test-pow-secret")
    monkeypatch.setattr(get_settings(), "cli_pow_difficulty", _DIFFICULTY)

    async def _noop(*_a: object, **_k: object) -> None:
        return None

    monkeypatch.setattr(scan_runner, "scan_run_upload", _noop)
    monkeypatch.setattr(scan_runner, "scan_run_repo", _noop)


def _remote_client(db_session: AsyncSession) -> AsyncClient:
    async def _override() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_session] = _override
    transport = ASGITransport(app=app, client=("203.0.113.9", 5555))
    return AsyncClient(transport=transport, base_url="http://test")


@pytest.mark.asyncio
async def test_cli_challenge_200(db_client: AsyncClient) -> None:
    r = await db_client.get("/api/v1/scans/cli-challenge")
    assert r.status_code == 200
    body = r.json()
    assert body["difficulty"] == _DIFFICULTY
    assert "." in body["challenge"]
    assert body["expires_at"]


@pytest.mark.asyncio
async def test_cli_challenge_503_when_unset(
    db_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "saferskills_cli_pow_secret", None)
    r = await db_client.get("/api/v1/scans/cli-challenge")
    assert r.status_code == 503
    assert r.json()["detail"]["error"] == "pow_unavailable"


@pytest.mark.asyncio
async def test_pow_passes_repo_submit_and_uses_cli_bucket(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    # Fetch a challenge over the (loopback) db_client, then submit over a remote
    # client carrying the solved header (no Turnstile token).
    ch = (await db_client.get("/api/v1/scans/cli-challenge")).json()
    solution = solve_pow(ch["challenge"], ch["difficulty"])
    header = {"X-SaferSkills-CLI-PoW": f"{ch['challenge']}.{solution}"}

    try:
        async with _remote_client(db_session) as ac:
            r = await ac.post(
                "/api/v1/scans",
                json={"github_url": "https://github.com/acme/x"},
                headers=header,
            )
        assert r.status_code == 202
    finally:
        app.dependency_overrides.pop(get_session, None)

    buckets = set(
        (await db_session.execute(text("SELECT DISTINCT bucket FROM rate_limits"))).scalars().all()
    )
    assert "cli_scan_submit" in buckets
    assert "scan_submit" not in buckets


@pytest.mark.asyncio
async def test_pow_passes_upload_submit(db_client: AsyncClient, db_session: AsyncSession) -> None:
    ch = (await db_client.get("/api/v1/scans/cli-challenge")).json()
    solution = solve_pow(ch["challenge"], ch["difficulty"])
    header = {"X-SaferSkills-CLI-PoW": f"{ch['challenge']}.{solution}"}
    files = {"file": ("SKILL.md", b"---\nname: t\n---\n# t\n", "text/markdown")}

    try:
        async with _remote_client(db_session) as ac:
            r = await ac.post(
                "/api/v1/scans/upload", files=files, data={"visibility": "public"}, headers=header
            )
        assert r.status_code == 202
    finally:
        app.dependency_overrides.pop(get_session, None)


@pytest.mark.asyncio
async def test_forged_pow_is_403(db_session: AsyncSession) -> None:
    header = {"X-SaferSkills-CLI-PoW": "bogus.deadbeef.1"}
    try:
        async with _remote_client(db_session) as ac:
            r = await ac.post(
                "/api/v1/scans",
                json={"github_url": "https://github.com/acme/x"},
                headers=header,
            )
        assert r.status_code == 403
        assert r.json()["detail"]["error"] == "pow_failed"
    finally:
        app.dependency_overrides.pop(get_session, None)
