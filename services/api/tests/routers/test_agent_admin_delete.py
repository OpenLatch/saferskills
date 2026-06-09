"""Admin delete of an Agent Report (I-5.5, AE-8). 403 without the key; with key ->
cascade + audit row; a public run is deletable ONLY via admin (not the token route)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AdminAuditLog
from app.models.generated.agent_finding import AgentFinding
from app.models.generated.agent_run import AgentRun


async def _published_public(db_client: AsyncClient) -> str:
    body: dict[str, Any] = (
        await db_client.post(
            "/api/v1/agent-scans",
            json={"agent_name": "a", "runtime": "claude-code", "visibility": "public"},
        )
    ).json()
    run_id, token = str(body["run_id"]), str(body["submit_token"])
    payload: dict[str, Any] = {
        "schema_version": "agent_scan_result.v1",
        "run_id": run_id,
        "pack_id": "p",
        "pack_version": "v",
        "capabilities_present": ["agent_response"],
        "tests": [{"test_id": "AS-01", "status": "executed", "turns": []}],
    }
    await db_client.post(
        f"/api/v1/agent-scans/{run_id}/submit",
        json=payload,
        headers={"X-Agent-Run-Token": str(token)},
    )
    return str(run_id)


@pytest.mark.asyncio
async def test_admin_delete_without_key_is_forbidden(
    db_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Force the fail-closed path: a configured key + no header -> 403.
    from app.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "saferskills_admin_key", "secret-key", raising=False)
    run_id = await _published_public(db_client)
    r = await db_client.delete(f"/api/v1/admin/agent-scans/{run_id}")
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_admin_delete_cascades_and_audits(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    run_id = await _published_public(db_client)
    # local-dev exemption: no key configured + ENV=development -> audits as local-dev.
    r = await db_client.delete(f"/api/v1/admin/agent-scans/{run_id}")
    assert r.status_code == 200
    assert r.json()["deleted"] is True

    assert await db_session.get(AgentRun, UUID(run_id)) is None
    remaining = (
        await db_session.execute(
            select(func.count())
            .select_from(AgentFinding)
            .where(AgentFinding.agent_run_id == UUID(run_id))
        )
    ).scalar_one()
    assert remaining == 0
    audits = (
        (
            await db_session.execute(
                select(AdminAuditLog).where(AdminAuditLog.action == "agent_scan_delete")
            )
        )
        .scalars()
        .all()
    )
    assert any(a.target == run_id for a in audits)


@pytest.mark.asyncio
async def test_admin_delete_absent_run_404(db_client: AsyncClient) -> None:
    r = await db_client.delete("/api/v1/admin/agent-scans/00000000-0000-0000-0000-000000000000")
    assert r.status_code == 404
