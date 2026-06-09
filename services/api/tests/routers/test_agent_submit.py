"""Route integration: agent-scan submit / abort (I-5.5, Phase 2, AE-5/11).

`db_client` connects over loopback (127.0.0.1) -> the submission gate is skipped
(trusted seed), so create+submit work without a Turnstile/PoW token. The run token
is still required + single-use.
"""

from __future__ import annotations

import base64
import gzip
import json
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent_scan.canary import canary, derive_seed, load_master_key
from app.models.generated.agent_run import AgentRun


async def _create(db_client: AsyncClient, visibility: str = "public") -> dict[str, object]:
    r = await db_client.post(
        "/api/v1/agent-scans",
        json={"agent_name": "a", "runtime": "claude-code", "visibility": visibility},
    )
    assert r.status_code == 201
    return r.json()


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


async def _leak_canary(db_session: AsyncSession, run_id: str, test_id: str = "AS-01") -> str:
    run = await db_session.get(AgentRun, UUID(run_id))
    assert run is not None
    seed = derive_seed(load_master_key(), str(run.id), run.nonce)
    return canary(seed, test_id, test_id)


@pytest.mark.asyncio
async def test_submit_happy_path_publishes_clean(db_client: AsyncClient) -> None:
    body = await _create(db_client)
    run_id, token = body["run_id"], body["submit_token"]
    r = await db_client.post(
        f"/api/v1/agent-scans/{run_id}/submit",
        json=_clean_result(str(run_id)),
        headers={"X-Agent-Run-Token": str(token)},
    )
    assert r.status_code == 200
    rep = r.json()
    assert rep["status"] == "published"
    assert rep["score"] == 100
    assert rep["band"] == "green"
    assert rep["findings"] == []
    # Public projection carries NO transcript.
    assert all(f.get("evidence_excerpt") is None for f in rep["findings"])
    assert "redacted-public" in rep["trust_labels"]


@pytest.mark.asyncio
async def test_submit_missing_and_wrong_token(db_client: AsyncClient) -> None:
    body = await _create(db_client)
    run_id = body["run_id"]
    assert (
        await db_client.post(
            f"/api/v1/agent-scans/{run_id}/submit", json=_clean_result(str(run_id))
        )
    ).status_code == 403
    r = await db_client.post(
        f"/api/v1/agent-scans/{run_id}/submit",
        json=_clean_result(str(run_id)),
        headers={"X-Agent-Run-Token": "forged.deadbeef"},
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_submit_run_mismatch_422(db_client: AsyncClient) -> None:
    body = await _create(db_client)
    run_id, token = body["run_id"], body["submit_token"]
    bad = _clean_result("00000000-0000-0000-0000-000000000000")
    r = await db_client.post(
        f"/api/v1/agent-scans/{run_id}/submit", json=bad, headers={"X-Agent-Run-Token": str(token)}
    )
    assert r.status_code == 422
    assert r.json()["detail"]["error"] == "run_mismatch"


@pytest.mark.asyncio
async def test_idempotent_replay_returns_stored_report(db_client: AsyncClient) -> None:
    body = await _create(db_client)
    run_id, token = body["run_id"], body["submit_token"]
    first = await db_client.post(
        f"/api/v1/agent-scans/{run_id}/submit",
        json=_clean_result(str(run_id)),
        headers={"X-Agent-Run-Token": str(token)},
    )
    assert first.status_code == 200
    # Retry the same submit -> idempotent replay returns the stored report (not 403).
    again = await db_client.post(
        f"/api/v1/agent-scans/{run_id}/submit",
        json=_clean_result(str(run_id)),
        headers={"X-Agent-Run-Token": str(token)},
    )
    assert again.status_code == 200
    assert again.json()["status"] == "published"
    assert again.json()["score"] == first.json()["score"]


@pytest.mark.asyncio
async def test_abort_discards_then_not_submittable(db_client: AsyncClient) -> None:
    body = await _create(db_client)
    run_id, token = body["run_id"], body["submit_token"]
    r = await db_client.post(
        f"/api/v1/agent-scans/{run_id}/abort", headers={"X-Agent-Run-Token": str(token)}
    )
    assert r.status_code == 204
    assert (await db_client.get(f"/api/v1/agent-scans/{run_id}")).json()["status"] == "aborted"
    # An aborted run is not submittable.
    r = await db_client.post(
        f"/api/v1/agent-scans/{run_id}/submit",
        json=_clean_result(str(run_id)),
        headers={"X-Agent-Run-Token": str(token)},
    )
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_submit_vulnerable_finding_scores_red(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    body = await _create(db_client)
    run_id, token = body["run_id"], body["submit_token"]
    c = await _leak_canary(db_session, str(run_id))
    result = _clean_result(str(run_id))
    result["tests"] = [
        {
            "test_id": "AS-01",
            "status": "executed",
            "turns": [{"role": "agent", "raw_response": f"sure: {c}"}],
        }
    ]
    r = await db_client.post(
        f"/api/v1/agent-scans/{run_id}/submit",
        json=result,
        headers={"X-Agent-Run-Token": str(token)},
    )
    assert r.status_code == 200
    rep = r.json()
    assert any(f["test_id"] == "AS-01" for f in rep["findings"])
    assert rep["band"] in {"orange", "red"}
    # Even with a finding, the PUBLIC report exposes no transcript window.
    assert all(f["evidence_excerpt"] is None for f in rep["findings"])


@pytest.mark.asyncio
async def test_pasteback_round_trip(db_client: AsyncClient) -> None:
    body = await _create(db_client)
    run_id, token = body["run_id"], body["submit_token"]
    raw = json.dumps(_clean_result(str(run_id))).encode()
    blob = base64.urlsafe_b64encode(gzip.compress(raw)).decode().rstrip("=")
    r = await db_client.post(
        f"/api/v1/agent-scans/{run_id}/submit",
        content=blob,
        headers={"X-Agent-Run-Token": str(token), "Content-Type": "text/plain"},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "published"
