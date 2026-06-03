"""Route integration: the Cloudflare Turnstile human gate on scan submit.

Pins the security contract for both scan-submit endpoints:
- a non-loopback caller with NO token is rejected `403 captcha_failed`;
- the verify runs BEFORE the idempotency cache (a bot can't farm a cached run);
- loopback callers (trusted seed) skip the gate entirely.

No network: a missing token short-circuits `verify_turnstile` to False without
any httpx call, and the worker is monkeypatched to a no-op.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.session import get_session
from app.main import app
from app.queue import scan_runner


@pytest.fixture(autouse=True)
def _gate_on(monkeypatch: pytest.MonkeyPatch) -> None:  # pyright: ignore[reportUnusedFunction]
    """Configure a secret (gate active) + stub the fire-and-forget workers."""
    monkeypatch.setattr(get_settings(), "turnstile_secret_key", "1x000...AA")

    async def _noop(*_a: object, **_k: object) -> None:
        return None

    monkeypatch.setattr(scan_runner, "scan_run_upload", _noop)
    monkeypatch.setattr(scan_runner, "scan_run_repo", _noop)


def _remote_client(db_session: AsyncSession) -> AsyncClient:
    """An AsyncClient whose TCP peer is a routable (non-loopback) IP — so the
    captcha gate + rate limit both apply — sharing the test's rolled-back session."""

    async def _override() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_session] = _override
    transport = ASGITransport(app=app, client=("203.0.113.9", 5555))
    return AsyncClient(transport=transport, base_url="http://test")


def _files(name: str = "SKILL.md", body: bytes = b"---\nname: t\n---\n# t\n"):
    return {"file": (name, body, "text/markdown")}


@pytest.mark.asyncio
async def test_repo_submit_without_token_is_403(db_session: AsyncSession) -> None:
    try:
        async with _remote_client(db_session) as ac:
            r = await ac.post("/api/v1/scans", json={"github_url": "https://github.com/acme/x"})
        assert r.status_code == 403
        assert r.json()["detail"]["error"] == "captcha_failed"
    finally:
        app.dependency_overrides.pop(get_session, None)


@pytest.mark.asyncio
async def test_upload_submit_without_token_is_403(db_session: AsyncSession) -> None:
    try:
        async with _remote_client(db_session) as ac:
            r = await ac.post("/api/v1/scans/upload", files=_files(), data={"visibility": "public"})
        assert r.status_code == 403
        assert r.json()["detail"]["error"] == "captcha_failed"
    finally:
        app.dependency_overrides.pop(get_session, None)


@pytest.mark.asyncio
async def test_loopback_is_exempt_even_with_gate_on(db_client: AsyncClient) -> None:
    """`db_client` connects over loopback (127.0.0.1) → the gate is skipped."""
    r = await db_client.post("/api/v1/scans/upload", files=_files(), data={"visibility": "public"})
    assert r.status_code == 202


@pytest.mark.asyncio
async def test_verify_precedes_cache_hit(db_client: AsyncClient, db_session: AsyncSession) -> None:
    """A loopback caller seeds a cached PUBLIC upload run (no token needed). A
    non-loopback bot POSTing identical bytes WITHOUT a token must be rejected
    403 — it can NOT farm the cached run by skipping verification."""
    seeded = await db_client.post(
        "/api/v1/scans/upload", files=_files(), data={"visibility": "public"}
    )
    assert seeded.status_code == 202

    try:
        async with _remote_client(db_session) as ac:
            r = await ac.post("/api/v1/scans/upload", files=_files(), data={"visibility": "public"})
        # 403 (gate), never a cached 200 — verify is ahead of the cache lookup.
        assert r.status_code == 403
        assert r.json()["detail"]["error"] == "captcha_failed"
    finally:
        app.dependency_overrides.pop(get_session, None)
