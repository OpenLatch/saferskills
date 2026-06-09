"""Route integration: the agent-scan run lifecycle (I-5.5, Phase 1).

Pins: create mints a run+token; the pack is token-gated (403 without, 200 with) +
substituted; the public GET projects a run (and 404s an unlisted one); the token
route serves the unlisted private projection with generic-404 on a bad token;
promote flips unlisted→public; the submission gate blocks a non-loopback caller.

`db_client` connects over loopback (127.0.0.1) → the submission gate is skipped
(trusted seed), so create works without a Turnstile/PoW token.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.session import get_session
from app.main import app


def _remote_client(db_session: AsyncSession) -> AsyncClient:
    async def _override() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_session] = _override
    transport = ASGITransport(app=app, client=("203.0.113.9", 5555))
    return AsyncClient(transport=transport, base_url="http://test")


@pytest.mark.asyncio
async def test_create_fetch_pack_and_get(db_client: AsyncClient) -> None:
    r = await db_client.post(
        "/api/v1/agent-scans",
        json={"agent_name": "my-agent", "runtime": "claude-code", "visibility": "public"},
    )
    assert r.status_code == 201
    body = r.json()
    run_id, token = body["run_id"], body["submit_token"]
    assert body["pack_url"] == f"/api/v1/agent-scans/{run_id}/pack"
    assert body["share_token"] is None

    # Pack without the run token → 403.
    r = await db_client.get(body["pack_url"])
    assert r.status_code == 403

    # With the token → 200, substituted, 20 tests.
    r = await db_client.get(body["pack_url"], headers={"X-Agent-Run-Token": token})
    assert r.status_code == 200
    pack = r.json()
    assert pack["result_schema"] == "agent_scan_result.v1"
    assert len(pack["tests"]) == 20
    assert "{{CANARY}}" not in r.text

    # Public projection now reports `fetched`.
    r = await db_client.get(f"/api/v1/agent-scans/{run_id}")
    assert r.status_code == 200
    assert r.json()["status"] == "fetched"
    assert r.json()["findings"] == []

    # Token-authed status poll.
    r = await db_client.get(
        f"/api/v1/agent-scans/{run_id}/status", headers={"X-Agent-Run-Token": token}
    )
    assert r.status_code == 200
    assert r.json()["status"] == "fetched"

    # Status poll without the token → 403.
    r = await db_client.get(f"/api/v1/agent-scans/{run_id}/status")
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_pack_keys_endpoint(db_client: AsyncClient) -> None:
    r = await db_client.get("/api/v1/agent-pack/keys")
    assert r.status_code == 200
    assert isinstance(r.json(), dict)  # empty in tests (no signing key configured)


@pytest.mark.asyncio
async def test_unlisted_view_generic404_and_promote(db_client: AsyncClient) -> None:
    r = await db_client.post(
        "/api/v1/agent-scans",
        json={"agent_name": "u", "runtime": "cursor", "visibility": "unlisted"},
    )
    assert r.status_code == 201
    body = r.json()
    run_id, share_token = body["run_id"], body["share_token"]
    assert share_token

    # Public route 404s an unlisted run.
    assert (await db_client.get(f"/api/v1/agent-scans/{run_id}")).status_code == 404

    # Token view → private projection with a share_url.
    r = await db_client.get(f"/api/v1/agent-scans/r/{share_token}")
    assert r.status_code == 200
    assert r.json()["visibility"] == "unlisted"
    assert r.json()["share_url"]
    assert r.headers["X-Robots-Tag"] == "noindex, nofollow"

    # Bad token → generic 404 (no oracle).
    assert (await db_client.get("/api/v1/agent-scans/r/not-a-real-token")).status_code == 404

    # Promote → public; the public route now serves it.
    r = await db_client.post(f"/api/v1/agent-scans/r/{share_token}/promote")
    assert r.status_code == 200
    assert r.json()["visibility"] == "public"
    assert (await db_client.get(f"/api/v1/agent-scans/{run_id}")).status_code == 200


@pytest.mark.asyncio
async def test_unlisted_delete_then_token_404(db_client: AsyncClient) -> None:
    body = (
        await db_client.post(
            "/api/v1/agent-scans",
            json={"agent_name": "d", "runtime": "codex", "visibility": "unlisted"},
        )
    ).json()
    token = body["share_token"]
    assert (await db_client.delete(f"/api/v1/agent-scans/r/{token}")).status_code == 204
    assert (await db_client.get(f"/api/v1/agent-scans/r/{token}")).status_code == 404


@pytest.mark.asyncio
async def test_submission_gate_blocks_non_loopback(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "turnstile_secret_key", "1xSECRET")
    try:
        async with _remote_client(db_session) as ac:
            r = await ac.post(
                "/api/v1/agent-scans",
                json={"agent_name": "a", "runtime": "codex", "visibility": "public"},
            )
        assert r.status_code == 403
        assert r.json()["detail"]["error"] == "captcha_failed"
    finally:
        app.dependency_overrides.pop(get_session, None)
