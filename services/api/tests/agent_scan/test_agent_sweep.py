"""Expiry sweeps (I-5.5, D-5.5-19). Expired unlisted runs + spent tokens are swept;
live + public rows survive."""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.sweeps import sweep_agent_run_tokens, sweep_agent_runs
from app.models.agent_run_token_spent import AgentRunTokenSpent
from app.models.generated.agent_run import AgentRun


def _run(*, visibility: str, expires_at: datetime | None) -> AgentRun:
    return AgentRun(
        status="published",
        agent_name="a",
        runtime="claude-code",
        band="green",
        pack_id="p",
        pack_version="v",
        visibility=visibility,
        rubric_version="r",
        engine_version="e",
        latency_ms=0,
        idempotency_key="tk-" + secrets.token_hex(6),
        nonce="n",
        share_token=(secrets.token_hex(8) if visibility == "unlisted" else None),
        expires_at=expires_at,
    )


@pytest.mark.asyncio
async def test_expired_unlisted_run_swept_live_survives(db_session: AsyncSession) -> None:
    now = datetime.now(UTC)
    expired = _run(visibility="unlisted", expires_at=now - timedelta(days=1))
    live = _run(visibility="unlisted", expires_at=now + timedelta(days=30))
    public = _run(visibility="public", expires_at=None)
    db_session.add_all([expired, live, public])
    await db_session.flush()
    expired_id, live_id, public_id = expired.id, live.id, public.id

    swept = await sweep_agent_runs(db_session)
    assert swept >= 1

    db_session.expire_all()  # the sweep deletes via Core SQL; drop the identity-map cache
    assert await db_session.get(AgentRun, expired_id) is None
    assert await db_session.get(AgentRun, live_id) is not None
    assert await db_session.get(AgentRun, public_id) is not None


@pytest.mark.asyncio
async def test_expired_token_swept(db_session: AsyncSession) -> None:
    now = datetime.now(UTC)
    dead = AgentRunTokenSpent(token_sha256="d" * 64, expires_at=now - timedelta(hours=1))
    alive = AgentRunTokenSpent(token_sha256="a" * 64, expires_at=now + timedelta(hours=1))
    db_session.add_all([dead, alive])
    await db_session.flush()

    swept = await sweep_agent_run_tokens(db_session)
    assert swept >= 1

    db_session.expire_all()  # the sweep deletes via Core SQL; drop the identity-map cache
    remaining = (
        await db_session.execute(select(func.count()).select_from(AgentRunTokenSpent))
    ).scalar_one()
    # The live token survives.
    assert (await db_session.get(AgentRunTokenSpent, "a" * 64)) is not None
    assert (await db_session.get(AgentRunTokenSpent, "d" * 64)) is None
    assert remaining >= 1
