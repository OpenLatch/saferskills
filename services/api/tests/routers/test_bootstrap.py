"""Route integration: the agent-scan bootstrap endpoint (I-5.5, Phase 3).

Pins: POST/GET `/agent-scans/bootstrap` mints a run + one-time token and renders a
platform prompt carrying the run_id + token + absolute pack/submit URLs; a bad
platform → 422; an unlisted run returns a `share_token`.

`db_client` connects over loopback (127.0.0.1) → the submission gate is skipped
(trusted seed), so bootstrap works without a Turnstile/PoW token.
"""

from __future__ import annotations

from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.generated.agent_run import AgentRun


@pytest.mark.asyncio
async def test_bootstrap_without_name_generates_codename(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Regression: omitting `agent_name` mints a distinct memorable codename, not
    the old shared `my-agent` placeholder (the directory used to show every card
    as 'my-agent')."""
    r = await db_client.post(
        "/api/v1/agent-scans/bootstrap",
        json={"platform": "claude-code", "visibility": "public"},
    )
    assert r.status_code == 201
    run = await db_session.get(AgentRun, UUID(r.json()["run_id"]))
    assert run is not None
    assert run.agent_name != "my-agent"
    assert "-" in run.agent_name  # adjective-noun shape


@pytest.mark.asyncio
async def test_bootstrap_post_mints_run_and_renders_prompt(db_client: AsyncClient) -> None:
    r = await db_client.post(
        "/api/v1/agent-scans/bootstrap",
        json={"platform": "claude-code", "agent_name": "my-agent", "visibility": "public"},
    )
    assert r.status_code == 201
    body = r.json()
    run_id, token = body["run_id"], body["submit_token"]

    # The prompt embeds the run id + the one-time token (the agent needs both).
    assert run_id in body["prompt"]
    assert token in body["prompt"]
    # Absolute, same-origin (public_base_url) pack/poll URLs the agent calls.
    assert body["pack_url"].endswith(f"/api/v1/agent-scans/{run_id}/pack")
    assert body["poll_url"].endswith(f"/api/v1/agent-scans/{run_id}/status")
    assert "/api/v1/agent-scans/" in body["pack_url"]
    assert body["consent_notice"]  # the company-telemetry notice + opt-out
    assert body["share_token"] is None  # public run

    # The minted run is fetchable + the token gates the pack (pack_url is absolute;
    # hit the relative path against the test transport).
    r = await db_client.get(f"/api/v1/agent-scans/{run_id}/pack")
    assert r.status_code == 403  # no token
    r = await db_client.get(
        f"/api/v1/agent-scans/{run_id}/pack", headers={"X-Agent-Run-Token": token}
    )
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_bootstrap_get_convenience(db_client: AsyncClient) -> None:
    r = await db_client.get("/api/v1/agent-scans/bootstrap", params={"platform": "universal"})
    assert r.status_code == 200
    body = r.json()
    assert body["run_id"] in body["prompt"]
    assert body["submit_token"]


@pytest.mark.asyncio
async def test_bootstrap_unlisted_returns_share_token(db_client: AsyncClient) -> None:
    r = await db_client.post(
        "/api/v1/agent-scans/bootstrap",
        json={"platform": "cursor", "visibility": "unlisted"},
    )
    assert r.status_code == 201
    assert r.json()["share_token"]


@pytest.mark.asyncio
async def test_every_platform_prompt_specifies_result_enums(db_client: AsyncClient) -> None:
    """Every platform's bootstrap prompt MUST spell out the closed
    `agent_scan_result.v1` enum sets. Otherwise an LLM defaults to standard chat
    roles (`user`/`assistant`/`system`) and a free-form `status`, and the strict
    submit schema 422s. Regression for the 8 terse agent templates that named only
    `skipped_capability_absent` and showed `{role, raw_response}` with no values.
    """
    from app.agent_scan.bootstrap import PLATFORMS

    for platform in sorted(PLATFORMS):
        r = await db_client.get("/api/v1/agent-scans/bootstrap", params={"platform": platform})
        assert r.status_code == 200, platform
        prompt = r.json()["prompt"]
        # The distinctive enum values an LLM would never guess on its own:
        assert "untrusted_input" in prompt, f"{platform}: role enum not specified"
        assert "executed" in prompt, f"{platform}: `executed` status not specified"
        assert "skipped_capability_absent" in prompt, platform


@pytest.mark.asyncio
async def test_bootstrap_bad_platform_422(db_client: AsyncClient) -> None:
    r = await db_client.post(
        "/api/v1/agent-scans/bootstrap",
        json={"platform": "not-a-real-platform", "visibility": "public"},
    )
    assert r.status_code == 422

    r = await db_client.get(
        "/api/v1/agent-scans/bootstrap", params={"platform": "not-a-real-platform"}
    )
    assert r.status_code == 422
