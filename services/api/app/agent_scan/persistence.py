"""Agent-scan persistence (I-5.5, Phase 1: run-create).

No catalog shadow row is created for an agent run — an Agent Report is its own
entity (`agent_runs`), NOT a catalog capability; the `/agents` directory (I-5.6)
reads `agent_runs`, never `catalog_items`. Grading/submit persistence + the full
`delete_agent_run_cascade` land in Phase 2.
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.agent_scan import canary as canary_mod
from app.agent_scan.pack import load_pack_source
from app.core.config import get_settings
from app.models.generated.agent_run import AgentRun

# Phase-1 engine tag for the behavioral scan (the deterministic grader is Phase 2).
AGENT_ENGINE_VERSION = "agent-scan-1"


async def create_agent_run(
    session: AsyncSession,
    *,
    agent_name: str,
    runtime: str,
    visibility: str,
) -> AgentRun:
    """Insert a fresh `agent_runs` row in `status='created'`.

    Mints the per-run `nonce` (canary seed input) + `decoy`; an unlisted run also
    mints an unguessable `share_token` + a 90-day `expires_at`. Records the pack
    identity so the run is reproducible.
    """
    source = load_pack_source()
    settings = get_settings()

    is_unlisted = visibility == "unlisted"
    share_token = secrets.token_urlsafe(32) if is_unlisted else None
    expires_at = (
        datetime.now(UTC) + timedelta(days=settings.unlisted_agent_retention_days)
        if is_unlisted
        else None
    )

    run = AgentRun(
        status="created",
        agent_name=agent_name,
        runtime=runtime,
        band="unscoped",
        pack_id=source["packId"],
        pack_version=source["packVersion"],
        visibility=visibility,
        rubric_version=source.get("packSha") or source["packVersion"],
        engine_version=AGENT_ENGINE_VERSION,
        latency_ms=0,
        idempotency_key=secrets.token_urlsafe(24),
        share_token=share_token,
        expires_at=expires_at,
        nonce=secrets.token_urlsafe(16),
        decoy=canary_mod.new_decoy(),
    )
    session.add(run)
    await session.flush()
    return run
