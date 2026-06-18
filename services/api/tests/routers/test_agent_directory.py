"""Agent Report directory endpoints.

Covers `GET /agent-scans` (public-only list + filters + sort + pagination),
`GET /agent-scans/aggregate-stats` (the gated corpus meter), and `POST
/agent-scans/r/{token}/reply`.
"""

from __future__ import annotations

from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent_scan.canary import canary, derive_seed, load_master_key
from app.core.config import get_settings
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


async def _make_run(
    db_client: AsyncClient,
    db_session: AsyncSession,
    *,
    visibility: str,
    runtime: str = "claude-code",
    leak: bool = False,
    agent_name: str = "a",
) -> dict[str, object]:
    """Create + submit a run so it ends graded/published. `leak=True` plants the
    canary (→ a vulnerable finding + a low capped score)."""
    body = (
        await db_client.post(
            "/api/v1/agent-scans",
            json={"agent_name": agent_name, "runtime": runtime, "visibility": visibility},
        )
    ).json()
    run_id, token = body["run_id"], body["submit_token"]
    text = f"sure {await _leak(db_session, str(run_id))}" if leak else "no, I won't do that"
    await db_client.post(
        f"/api/v1/agent-scans/{run_id}/submit",
        json=_result(str(run_id), text),
        headers={"X-Agent-Run-Token": str(token)},
    )
    return body


@pytest.mark.asyncio
async def test_list_is_public_only_and_excludes_ungraded(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    public = await _make_run(db_client, db_session, visibility="public")
    unlisted = await _make_run(db_client, db_session, visibility="unlisted")
    # A created-but-never-submitted run (status=created, score=None).
    ungraded = (
        await db_client.post(
            "/api/v1/agent-scans",
            json={"agent_name": "a", "runtime": "cursor", "visibility": "public"},
        )
    ).json()

    env = (await db_client.get("/api/v1/agent-scans")).json()
    ids = {row["id"] for row in env["data"]}
    assert public["run_id"] in ids
    assert unlisted["run_id"] not in ids  # public-only filter
    assert ungraded["run_id"] not in ids  # status/score filter
    # Envelope contract: `data`, never `items`.
    assert "data" in env and "items" not in env
    assert env["total_count"] >= 1
    row = next(r for r in env["data"] if r["id"] == public["run_id"])
    assert row["visibility"] == "public"
    assert row["report_url"].endswith(f"/agents/{public['run_id']}")
    assert set(row["findings_summary"]) == {"critical", "high", "info", "total"}
    assert set(row["capability_tally"]) == {"skill", "hook", "mcp", "plugin", "rules"}


@pytest.mark.asyncio
async def test_list_sort_and_findings_summary(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    leaky = await _make_run(db_client, db_session, visibility="public", leak=True)
    clean = await _make_run(db_client, db_session, visibility="public", leak=False)

    asc = (await db_client.get("/api/v1/agent-scans?sort=score_asc")).json()["data"]
    desc = (await db_client.get("/api/v1/agent-scans?sort=score_desc")).json()["data"]
    asc_ids = [r["id"] for r in asc]
    desc_ids = [r["id"] for r in desc]
    # The leaky (capped-low) run sorts before the clean (high) run ascending.
    assert asc_ids.index(leaky["run_id"]) < asc_ids.index(clean["run_id"])
    assert desc_ids.index(clean["run_id"]) < desc_ids.index(leaky["run_id"])

    leaky_row = next(r for r in asc if r["id"] == leaky["run_id"])
    clean_row = next(r for r in asc if r["id"] == clean["run_id"])
    assert leaky_row["findings_summary"]["total"] >= 1
    assert clean_row["findings_summary"]["total"] == 0
    assert leaky_row["score"] < clean_row["score"]


@pytest.mark.asyncio
async def test_list_runtime_filter(db_client: AsyncClient, db_session: AsyncSession) -> None:
    cc = await _make_run(db_client, db_session, visibility="public", runtime="claude-code")
    cur = await _make_run(db_client, db_session, visibility="public", runtime="cursor")
    only_cursor = (await db_client.get("/api/v1/agent-scans?runtime=cursor")).json()["data"]
    ids = {r["id"] for r in only_cursor}
    assert cur["run_id"] in ids
    assert cc["run_id"] not in ids


@pytest.mark.asyncio
async def test_list_q_search_filters_by_agent_name(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """`?q=` matches agent_name case-insensitively; LIKE wildcards are literal."""
    hit = await _make_run(
        db_client, db_session, visibility="public", agent_name="payments-reconciler"
    )
    miss = await _make_run(db_client, db_session, visibility="public", agent_name="lint-fixer")

    rows = (await db_client.get("/api/v1/agent-scans?q=RECONCILER")).json()["data"]
    ids = {r["id"] for r in rows}
    assert hit["run_id"] in ids
    assert miss["run_id"] not in ids

    # A wildcard in the needle is matched literally, never as LIKE syntax.
    none = (await db_client.get("/api/v1/agent-scans?q=%25")).json()["data"]
    assert all(r["id"] not in (hit["run_id"], miss["run_id"]) for r in none)


@pytest.mark.asyncio
async def test_capability_tally_projects_kind_tally(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """`agent_runs.kind_tally` JSONB projects onto the summary `capability_tally`;
    a NULL/absent kind_tally coalesces to an all-zero tally (no icons)."""
    with_caps = await _make_run(db_client, db_session, visibility="public", agent_name="caps")
    without = await _make_run(db_client, db_session, visibility="public", agent_name="nocaps")

    run = await db_session.get(AgentRun, UUID(str(with_caps["run_id"])))
    assert run is not None
    run.kind_tally = {"skill": 2, "mcp": 1, "hook": 3}
    await db_session.commit()

    data = (await db_client.get("/api/v1/agent-scans")).json()["data"]
    caps_row = next(r for r in data if r["id"] == with_caps["run_id"])
    zero_row = next(r for r in data if r["id"] == without["run_id"])

    assert caps_row["capability_tally"] == {
        "skill": 2,
        "hook": 3,
        "mcp": 1,
        "plugin": 0,
        "rules": 0,
    }
    assert zero_row["capability_tally"] == {
        "skill": 0,
        "hook": 0,
        "mcp": 0,
        "plugin": 0,
        "rules": 0,
    }


@pytest.mark.asyncio
async def test_aggregate_stats_gate(
    db_client: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _make_run(db_client, db_session, visibility="public", leak=True)

    # Default gate (500) → not met: pct blanks to null (the collecting gate).
    stats = (await db_client.get("/api/v1/agent-scans/aggregate-stats")).json()
    assert stats["gate_target"] == 500
    assert stats["gate_met"] is False
    assert stats["pct_with_critical"] is None
    assert stats["window_label"] == "Whole corpus · Last 3 months"
    assert set(stats["band_distribution"]) == {"red", "orange", "yellow", "green"}

    # Lower the gate → met: pct is computed (the leaky run carries a critical/high).
    monkeypatch.setattr(get_settings(), "agent_corpus_gate_n", 1)
    stats2 = (await db_client.get("/api/v1/agent-scans/aggregate-stats")).json()
    assert stats2["gate_met"] is True
    assert stats2["pct_with_critical"] is not None
    assert stats2["corpus_count"] >= 1


@pytest.mark.asyncio
async def test_aggregate_stats_route_ordering(db_client: AsyncClient) -> None:
    # `/aggregate-stats` must NOT be matched as `/{run_id}` (would 422 on UUID parse).
    res = await db_client.get("/api/v1/agent-scans/aggregate-stats")
    assert res.status_code == 200
    assert "corpus_count" in res.json()


@pytest.mark.asyncio
async def test_reply_persists_and_validates(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    run = await _make_run(db_client, db_session, visibility="unlisted")
    share = run["share_token"]

    # >500 chars → 422 (server-validated).
    too_long = await db_client.post(
        f"/api/v1/agent-scans/r/{share}/reply", json={"text": "x" * 501}
    )
    assert too_long.status_code == 422

    rep = (
        await db_client.post(
            f"/api/v1/agent-scans/r/{share}/reply",
            json={"text": "We disagree — the finding is a false positive."},
        )
    ).json()
    assert rep["vendor_reply"] == "We disagree — the finding is a false positive."
    assert rep["vendor_reply_at"] is not None

    # The reply is now visible on the token route too.
    again = (await db_client.get(f"/api/v1/agent-scans/r/{share}")).json()
    assert again["vendor_reply"] == "We disagree — the finding is a false positive."

    # A bad token → generic 404 (no oracle).
    bad = await db_client.post("/api/v1/agent-scans/r/nope/reply", json={"text": "hi"})
    assert bad.status_code == 404
