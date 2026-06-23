"""Regression: the agent-scan result-submission endpoint is NOT CAPTCHA-gated.

The intended caller of `POST /agent-scans/{run_id}/submit` is the AI agent itself,
which posts with ONLY an `X-Agent-Run-Token` header — no Turnstile token, no
CLI-PoW. The existing `test_agent_submit.py` mints+submits over loopback
(`db_client` = 127.0.0.1), which skips the gate entirely, so it can't see the bug.

This test exercises submit from a **non-loopback** peer with a **configured**
Turnstile secret (the gate would actively reject). On `main` the handler runs
`_gate_agent_submission` before the token check, so a tokenless-CAPTCHA agent gets
`403 captcha_failed`. With the gate removed, the run token alone authorizes the
submit -> `200` + a published report.

Mirrors `test_captcha_gate.py::test_verify_precedes_cache_hit`: seed over loopback
(`db_client`), then hit from `_remote_client` sharing the rolled-back `db_session`.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.session import get_session
from app.main import app


@pytest.fixture(autouse=True)
def _gate_on(monkeypatch: pytest.MonkeyPatch) -> None:  # pyright: ignore[reportUnusedFunction]
    """A configured Turnstile secret makes the human/bot gate active — so if the
    submit handler still gated, a tokenless agent POST would be rejected."""
    monkeypatch.setattr(get_settings(), "turnstile_secret_key", "1x000...AA")


def _remote_client(db_session: AsyncSession) -> AsyncClient:
    """An AsyncClient whose TCP peer is routable (non-loopback) — so any gate
    would apply — sharing the test's rolled-back session."""

    async def _override() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_session] = _override
    transport = ASGITransport(app=app, client=("203.0.113.9", 5555))
    return AsyncClient(transport=transport, base_url="http://test")


def _clean_result(run_id: str) -> dict[str, object]:
    return {
        "schema_version": "agent_scan_result.v1",
        "run_id": run_id,
        "pack_id": "p",
        "pack_version": "v",
        "pack_signature_verified": False,
        "capabilities_present": ["agent_response"],
        "tests": [
            {
                "test_id": "AS-01",
                "status": "executed",
                "turns": [{"role": "agent", "raw_response": "refused"}],
            }
        ],
    }


@pytest.mark.asyncio
async def test_non_loopback_submit_needs_only_run_token(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """A loopback caller mints a run (gate-exempt). A non-loopback agent then
    POSTs the result with ONLY the run token — no Turnstile, no PoW — and must
    get `200` + a published report. On `main` this returns `403 captcha_failed`."""
    minted = await db_client.post(
        "/api/v1/agent-scans",
        json={"agent_name": "a", "runtime": "claude-code", "visibility": "public"},
    )
    assert minted.status_code == 201
    body = minted.json()
    run_id, token = body["run_id"], body["submit_token"]

    try:
        async with _remote_client(db_session) as ac:
            r = await ac.post(
                f"/api/v1/agent-scans/{run_id}/submit",
                json=_clean_result(str(run_id)),
                headers={"X-Agent-Run-Token": str(token)},
            )
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "published"
    finally:
        app.dependency_overrides.pop(get_session, None)


@pytest.mark.asyncio
async def test_non_loopback_mint_still_gated(db_session: AsyncSession) -> None:
    """The mint endpoint keeps its full gate: a non-loopback POST to
    `/agent-scans` with no Turnstile/PoW is still rejected `403 captcha_failed`."""
    try:
        async with _remote_client(db_session) as ac:
            r = await ac.post(
                "/api/v1/agent-scans",
                json={"agent_name": "a", "runtime": "claude-code", "visibility": "public"},
            )
        assert r.status_code == 403
        assert r.json()["detail"]["error"] == "captcha_failed"
    finally:
        app.dependency_overrides.pop(get_session, None)
