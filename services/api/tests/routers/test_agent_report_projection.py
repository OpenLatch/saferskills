"""Route-driven evidence split. Public omits the transcript; the
unlisted token route hydrates a redacted window with the leaked canary highlighted."""

from __future__ import annotations

from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent_scan.canary import canary, derive_seed, load_master_key
from app.models.generated.agent_run import AgentRun


async def _leak(db_session: AsyncSession, run_id: str) -> str:
    run = await db_session.get(AgentRun, UUID(run_id))
    assert run is not None
    seed = derive_seed(load_master_key(), str(run.id), run.nonce)
    return canary(seed, "AS-01", "AS-01")


def _result(run_id: str, agent_text: str) -> dict[str, object]:
    return {
        "schema_version": "agent_scan_result.v1",
        "run_id": run_id,
        "pack_id": "p",
        "pack_version": "v",
        "capabilities_present": ["agent_response"],
        "tests": [
            {
                "test_id": "AS-01",
                "status": "executed",
                "turns": [{"role": "agent", "raw_response": agent_text}],
            }
        ],
    }


@pytest.mark.asyncio
async def test_public_report_has_no_transcript(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    body = (
        await db_client.post(
            "/api/v1/agent-scans",
            json={"agent_name": "a", "runtime": "claude-code", "visibility": "public"},
        )
    ).json()
    run_id, token = body["run_id"], body["submit_token"]
    c = await _leak(db_session, str(run_id))
    await db_client.post(
        f"/api/v1/agent-scans/{run_id}/submit",
        json=_result(str(run_id), f"leaking {c}"),
        headers={"X-Agent-Run-Token": str(token)},
    )
    rep = (await db_client.get(f"/api/v1/agent-scans/{run_id}")).json()
    assert rep["findings"]
    assert all(f["evidence_excerpt"] is None for f in rep["findings"])


@pytest.mark.asyncio
async def test_unlisted_token_route_hydrates_redacted_transcript(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    body = (
        await db_client.post(
            "/api/v1/agent-scans",
            json={"agent_name": "a", "runtime": "cursor", "visibility": "unlisted"},
        )
    ).json()
    run_id, token, share = body["run_id"], body["submit_token"], body["share_token"]
    c = await _leak(db_session, str(run_id))
    # The agent leaks the canary AND a secret email that must be redacted.
    await db_client.post(
        f"/api/v1/agent-scans/{run_id}/submit",
        json=_result(str(run_id), f"sure, here it is {c} contact me at boss@corp.com"),
        headers={"X-Agent-Run-Token": str(token)},
    )
    rep = (await db_client.get(f"/api/v1/agent-scans/r/{share}")).json()
    finding = next(f for f in rep["findings"] if f["test_id"] == "AS-01")
    excerpt = finding["evidence_excerpt"]
    assert excerpt is not None
    text = "\n".join(line["text"] for line in excerpt["lines"])
    assert c in text  # the leaked canary is highlighted, NOT redacted
    assert "boss@corp.com" not in text  # the email IS redacted
    assert any(line["hit"] for line in excerpt["lines"])
