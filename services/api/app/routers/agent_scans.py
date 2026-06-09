"""Agent-scan run-lifecycle surface (I-5.5, Phase 1).

Mints a run + one-time submit token, serves the per-run Ed25519-signed pack
(token-gated, 410 after submit), exposes the flat pubkey map, and reuses the
I-3.5 unlisted capability-URL contract (token view / promote / delete) verbatim.
Grading + submit + the company-level telemetry land in Phase 2.

Reuses the stable submission-gate + unlisted helpers from `app.routers.scans`
(single source of truth for the trusted-proxy client-IP + generic-404 + anti-
leakage behaviour). The PUBLIC `GET /{run_id}` route NEVER loads `agent_evidence`
(it carries the private transcript) — Codex#7.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent_scan import pack as pack_mod
from app.agent_scan import signing
from app.agent_scan.canary import derive_seed, load_master_key
from app.agent_scan.persistence import create_agent_run
from app.agent_scan.report import build_agent_report
from app.agent_scan.run_token import RunTokenError, mint_submit_token, verify_run_token
from app.core.config import Settings, get_settings
from app.core.rate_limit import enforce_ip_rate_limit
from app.db.session import get_session
from app.models.agent_evidence import AgentEvidence
from app.models.generated.agent_run import AgentRun
from app.routers.scans import (
    enforce_captcha,
    enforce_private_lookup_limit,
    is_loopback,
    peer_host,
    rate_limit_ip,
    set_unlisted_headers,
)
from app.schemas.agent_scan import (
    AgentScanCreateRequest,
    AgentScanCreateResponse,
    AgentScanReportDetail,
    AgentScanStatusResponse,
)
from app.services.cli_pow import PowDisabled, PowRejected, verify_pow

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agent-scans", tags=["agent-scans"])
# `GET /api/v1/agent-pack/keys` lives off a sibling prefix (not /agent-scans).
pack_keys_router = APIRouter(prefix="/agent-pack", tags=["agent-scans"])

# Statuses past which a pack must NEVER be re-served (the canaries are spent).
_PACK_CLOSED_STATES = frozenset({"submitted", "graded", "published", "aborted"})


def _is_live_unlisted(run: AgentRun | None) -> bool:
    """True only for a present, unlisted, unexpired run — else the route 404s
    generically (no existence/expiry oracle). Mirrors `scans._is_live_unlisted`."""
    if run is None or run.visibility != "unlisted":
        return False
    return not (run.expires_at is not None and run.expires_at < datetime.now(UTC))


async def _gate_agent_submission(
    request: Request, session: AsyncSession, *, settings: Settings
) -> None:
    """Human/bot gate for `POST /agent-scans` (D-5.5-15). Loopback-exempt at the
    call site. PoW path (CLI) elif Turnstile (browser) — both count against the
    dedicated `agent_scan_submit` bucket. Verify precedes the rate-limit + the mint."""
    ip = rate_limit_ip(request, settings)
    pow_header = request.headers.get("x-saferskills-cli-pow")
    turnstile_token = request.headers.get("cf-turnstile-response")
    if pow_header and not turnstile_token:
        try:
            await verify_pow(pow_header, session)
        except PowDisabled as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail={"error": "pow_unavailable"}
            ) from exc
        except PowRejected as exc:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail={"error": "pow_failed"}
            ) from exc
    else:
        await enforce_captcha(request)
    await enforce_ip_rate_limit(
        session, ip=ip, bucket="agent_scan_submit", limit=settings.agent_scan_submit_daily_limit
    )


@router.post("", status_code=status.HTTP_201_CREATED, response_model=AgentScanCreateResponse)
async def create_run(
    body: AgentScanCreateRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> AgentScanCreateResponse:
    """Mint a run + one-time submit token; return the token-gated pack URL."""
    settings = get_settings()
    if not is_loopback(peer_host(request)):
        await _gate_agent_submission(request, session, settings=settings)

    run = await create_agent_run(
        session,
        agent_name=body.agent_name,
        runtime=body.runtime,
        visibility=body.visibility,
    )
    token = mint_submit_token(str(run.id))
    await session.commit()

    return AgentScanCreateResponse(
        run_id=run.id,
        submit_token=token,
        pack_url=f"/api/v1/agent-scans/{run.id}/pack",
        expires_at=run.expires_at,
        share_token=run.share_token,
    )


@router.get("/{run_id}/pack")
async def get_pack(
    run_id: UUID,
    x_agent_run_token: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Serve the per-run Ed25519-signed pack (token-gated, 410 after submit).

    Token verify is NO-spend (the agent + CLI each pre-flight a fetch). Refuses to
    re-serve once the run is past `fetched` (the canaries are spent → 410). Archives
    the exact served bytes + signature for reproducibility and advances to
    `fetched`.
    """
    run = await session.get(AgentRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="not found")
    try:
        verify_run_token(x_agent_run_token, str(run_id))
    except RunTokenError as exc:
        raise HTTPException(status_code=403, detail={"error": "bad_run_token"}) from exc
    if run.status in _PACK_CLOSED_STATES:
        raise HTTPException(status_code=410, detail={"error": "pack_closed"})

    seed = derive_seed(load_master_key(), str(run.id), run.nonce)
    body = pack_mod.assemble_pack(seed=seed, decoy=run.decoy or "")
    key_id, sig = signing.sign_pack(body)
    sha256 = hashlib.sha256(body).hexdigest()

    # Archive the served bytes (idempotent — a re-fetch derives identical bytes).
    await session.execute(
        pg_insert(AgentEvidence)
        .values(agent_run_id=run.id, pack_bytes=body, byte_size=len(body))
        .on_conflict_do_update(
            index_elements=["agent_run_id"],
            set_={"pack_bytes": body, "byte_size": len(body)},
        )
    )
    await session.execute(
        update(AgentRun)
        .where(AgentRun.id == run.id)
        .values(
            pack_sha256=sha256,
            pack_signature=sig or None,
            pack_key_id=key_id or None,
            status="fetched",
        )
    )
    await session.commit()

    headers = {"Cache-Control": "no-store"}
    if sig:
        headers["X-Pack-Key-Id"] = key_id
        headers["X-Pack-Signature"] = sig
    return Response(content=body, media_type="application/json", headers=headers)


@pack_keys_router.get("/keys")
async def get_pack_keys() -> dict[str, str]:
    """Flat `{key_id: base64-pubkey}` map (config-sourced, no DB)."""
    return signing.public_keys()


@router.get("/r/{token}", response_model=AgentScanReportDetail)
async def get_unlisted_run(
    token: str,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
) -> AgentScanReportDetail | Response:
    """View an unlisted Agent Report via its share token (private projection).

    Invalid / expired / deleted / not-unlisted ALL → generic 404 (no oracle). A
    promoted (now-public) run 307-redirects to the public report route."""
    await enforce_private_lookup_limit(request, session)
    run = (
        await session.execute(select(AgentRun).where(AgentRun.share_token == token))
    ).scalar_one_or_none()
    if run is not None and run.visibility == "public":
        return RedirectResponse(
            url=f"/api/v1/agent-scans/{run.id}", status_code=status.HTTP_307_TEMPORARY_REDIRECT
        )
    if not _is_live_unlisted(run):
        raise HTTPException(status_code=404, detail="not found")
    assert run is not None
    set_unlisted_headers(response)
    return build_agent_report(run, settings=get_settings(), private=True)


@router.post("/r/{token}/promote", response_model=AgentScanReportDetail)
async def promote_unlisted_run(
    token: str,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
) -> AgentScanReportDetail:
    """Promote an unlisted run to public (one-way): clear the token + expiry."""
    await enforce_private_lookup_limit(request, session)
    run = (
        await session.execute(select(AgentRun).where(AgentRun.share_token == token))
    ).scalar_one_or_none()
    if run is None or (run.visibility != "public" and not _is_live_unlisted(run)):
        raise HTTPException(status_code=404, detail="not found")
    if run.visibility != "public":
        run.visibility = "public"
        run.share_token = None
        run.expires_at = None
        await session.commit()
        await session.refresh(run)
    set_unlisted_headers(response)
    return build_agent_report(run, settings=get_settings(), private=False)


@router.delete("/r/{token}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_unlisted_run(
    token: str,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Eager self-delete of an unlisted run (Phase 1: the run row + its FK-CASCADE
    children; the full `delete_agent_run_cascade` lands in Phase 2). Public → 404."""
    await enforce_private_lookup_limit(request, session)
    run = (
        await session.execute(select(AgentRun).where(AgentRun.share_token == token))
    ).scalar_one_or_none()
    if not _is_live_unlisted(run):
        raise HTTPException(status_code=404, detail="not found")
    assert run is not None
    # FK CASCADE removes agent_findings + agent_evidence; agent_scan_telemetry is
    # SET NULL (the anonymous aggregate survives). The token ledger is keyed by
    # hash and reaped by the expiry sweep (Phase 2), not run-cascaded.
    await session.execute(delete(AgentRun).where(AgentRun.id == run.id))
    await session.commit()
    set_unlisted_headers(response)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{run_id}", response_model=AgentScanReportDetail)
async def get_run(
    run_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> AgentScanReportDetail:
    """Public projection of a run. 404 for unlisted runs (served only via the token
    route). NEVER loads `agent_evidence` — the public report carries no transcript."""
    run = await session.get(AgentRun, run_id)
    if run is None or run.visibility != "public":
        raise HTTPException(status_code=404, detail="not found")
    return build_agent_report(run, settings=get_settings(), private=False)


@router.get("/{run_id}/status", response_model=AgentScanStatusResponse)
async def get_run_status(
    run_id: UUID,
    x_agent_run_token: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
) -> AgentScanStatusResponse:
    """Token-authed lightweight poll — the poll target for BOTH public + unlisted
    runs (the `private_lookup` cap is too low for ~120 polls a 3-min scan needs)."""
    run = await session.get(AgentRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="not found")
    try:
        verify_run_token(x_agent_run_token, str(run_id))
    except RunTokenError as exc:
        raise HTTPException(status_code=403, detail={"error": "bad_run_token"}) from exc
    settings = get_settings()
    private = run.visibility == "unlisted"
    report = build_agent_report(run, settings=settings, private=private)
    return AgentScanStatusResponse(
        status=run.status,
        score=run.score,
        band=run.band if run.score is not None else None,
        report_url=report.report_url,
        share_url=report.share_url,
    )
