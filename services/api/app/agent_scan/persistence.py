"""Agent-scan persistence (I-5.5, Phase 1: run-create).

No catalog shadow row is created for an agent run - an Agent Report is its own
entity (`agent_runs`), NOT a catalog capability; the `/agents` directory (I-5.6)
reads `agent_runs`, never `catalog_items`. Grading/submit persistence + the full
`delete_agent_run_cascade` land in Phase 2.
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent_scan import canary as canary_mod
from app.agent_scan.grading import GradeOutcome
from app.agent_scan.pack import load_pack_source
from app.core.config import get_settings
from app.models.agent_evidence import AgentEvidence
from app.models.agent_scan_telemetry import AgentScanTelemetry
from app.models.generated.agent_finding import AgentFinding
from app.models.generated.agent_run import AgentRun
from app.schemas.agent_scan import AgentScanResultV1

# Phase-1 engine tag for the behavioral scan (the deterministic grader is Phase 2).
AGENT_ENGINE_VERSION = "agent-scan-1"


class PublicRunDeletionRefused(Exception):
    """`delete_agent_run_cascade` refused to delete a public run (caller lacked
    `allow_public`). Only the admin runbook deletes a public Agent Report."""


async def create_agent_run(
    session: AsyncSession,
    *,
    agent_name: str,
    runtime: str,
    visibility: str,
    component_scan_run_id: UUID | None = None,
    kind_tally: dict[str, int] | None = None,
) -> AgentRun:
    """Insert a fresh `agent_runs` row in `status='created'`.

    Mints the per-run `nonce` (canary seed input) + `decoy`; an unlisted run also
    mints an unguessable `share_token` + a 90-day `expires_at`. Records the pack
    identity so the run is reproducible.

    `component_scan_run_id` links a best-effort CLI-captured component scan_run (the
    `scan --local` upload of the scanned platform's installed capabilities) so the
    report can project its per-capability `scans` into the Component Scores tab;
    `kind_tally` is the per-kind capability inventory backing the `/agents` dossier
    icons. Both are null on web/`--print-skill` paths (no local filesystem).
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
        component_scan_run_id=component_scan_run_id,
        kind_tally=kind_tally,
    )
    session.add(run)
    await session.flush()
    return run


async def store_evidence(session: AsyncSession, run_id: UUID, result: AgentScanResultV1) -> None:
    """Upsert the submitted raw `agent_scan_result.v1` onto the per-run evidence row
    (the pack_bytes archived at fetch are preserved)."""
    payload = result.model_dump(by_alias=False)
    await session.execute(
        pg_insert(AgentEvidence)
        .values(agent_run_id=run_id, result_json=payload)
        .on_conflict_do_update(index_elements=["agent_run_id"], set_={"result_json": payload})
    )


async def load_findings(session: AsyncSession, run_id: UUID) -> list[AgentFinding]:
    """All `agent_findings` rows for a run (the vulnerable verdicts), id-ordered."""
    rows = await session.execute(
        select(AgentFinding)
        .where(AgentFinding.agent_run_id == run_id)
        .order_by(AgentFinding.test_id)
    )
    return list(rows.scalars().all())


async def persist_grade(
    session: AsyncSession,
    run: AgentRun,
    result: AgentScanResultV1,
    outcome: GradeOutcome,
    *,
    latency_ms: int,
    opted_out: bool,
) -> None:
    """Insert the vulnerable `agent_findings` rows + advance the run to `published`.

    `trust_labels` gains `redacted-public` (public runs) + `metadata-opted-out`
    (opted out) on top of the grading-intrinsic labels. Caller commits."""
    for finding in outcome.findings:
        session.add(
            AgentFinding(
                agent_run_id=run.id,
                test_id=finding.test_id,
                severity=finding.severity,
                verdict="vulnerable",
                family=finding.family,
                owasp_refs=finding.owasp_refs,
                atlas_refs=finding.atlas_refs,
                nist_refs=finding.nist_refs,
                score_delta=finding.score_delta,
                detection_rule=finding.detection_rule,
                leaked_canary_slot=finding.leaked_canary_slot,
            )
        )

    labels = list(outcome.trust_labels)
    if run.visibility == "public":
        labels.append("redacted-public")
    if opted_out:
        labels.append("metadata-opted-out")

    run.score = outcome.score
    run.band = outcome.band
    run.verdict_label = outcome.verdict_label
    run.cap_callout = outcome.cap_callout
    run.confidence = outcome.confidence
    run.score_breakdown = outcome.score_breakdown
    run.trust_labels = labels
    run.family_tally = outcome.family_tally
    run.capabilities_present = list(result.capabilities_present)
    run.capabilities_absent = list(result.capabilities_absent)
    run.pack_signature_verified = result.pack_signature_verified
    run.latency_ms = latency_ms
    run.scanned_at = datetime.now(UTC)
    run.status = "published"


async def delete_agent_run_cascade(
    session: AsyncSession, run_id: UUID, *, allow_public: bool = False
) -> bool:
    """Ordered delete of an agent run + its children. Returns False if absent.

    Order: findings -> telemetry (full erase) -> evidence -> run. The order is
    driven by logical ownership, not a DB constraint — `agent_findings`/`evidence`
    FK CASCADE and `agent_scan_telemetry` FK SET-NULLs, so an explicit child-first
    delete is what makes telemetry a FULL erase (not a SET NULL) on a vendor/abuse
    delete. NEVER touches `artifact_blobs`; the `agent_run_token_spent` ledger is
    keyed by token hash and reaped only by `sweep_agent_run_tokens` (NOT cascaded,
    Codex#10). Refuses a public run unless `allow_public` (admin runbook only)."""
    run = await session.get(AgentRun, run_id)
    if run is None:
        return False
    if run.visibility == "public" and not allow_public:
        raise PublicRunDeletionRefused(str(run_id))
    await session.execute(delete(AgentFinding).where(AgentFinding.agent_run_id == run_id))
    await session.execute(
        delete(AgentScanTelemetry).where(AgentScanTelemetry.agent_run_id == run_id)
    )
    await session.execute(delete(AgentEvidence).where(AgentEvidence.agent_run_id == run_id))
    await session.execute(delete(AgentRun).where(AgentRun.id == run_id))
    return True
