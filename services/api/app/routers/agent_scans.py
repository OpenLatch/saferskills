"""Agent-scan run-lifecycle surface.

Mints a run + one-time submit token, serves the per-run Ed25519-signed pack
(token-gated, 410 after submit), exposes the flat pubkey map, and reuses the
unlisted capability-URL contract (token view / promote / delete) verbatim.
Grading + submit + the company-level telemetry land separately.

Reuses the stable submission-gate + unlisted helpers from `app.routers.scans`
(single source of truth for the trusted-proxy client-IP + generic-404 + anti-
leakage behaviour). The PUBLIC `GET /{run_id}` route NEVER loads `agent_evidence`
(it carries the private transcript).
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response, status
from fastapi.responses import RedirectResponse
from pydantic import ValidationError
from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent_scan import bootstrap as bootstrap_mod
from app.agent_scan import directory as directory_mod
from app.agent_scan import pack as pack_mod
from app.agent_scan import signing
from app.agent_scan import telemetry as telemetry_mod
from app.agent_scan.canary import derive_seed, load_master_key
from app.agent_scan.components import render_agent_report
from app.agent_scan.grading import grade
from app.agent_scan.naming import resolve_agent_name
from app.agent_scan.pasteback import decode_pasteback
from app.agent_scan.persistence import (
    create_agent_run,
    delete_agent_run_cascade,
    load_findings,
    persist_grade,
    store_evidence,
)
from app.agent_scan.report import report_urls
from app.agent_scan.run_token import (
    RunTokenError,
    mint_submit_token,
    verify_run_token,
    verify_submit_token,
)
from app.core.config import Settings, get_settings
from app.core.rate_limit import enforce_ip_rate_limit
from app.db.session import get_session
from app.models.agent_evidence import AgentEvidence
from app.models.generated.agent_run import AgentRun
from app.models.generated.scan_run import ScanRun
from app.observability import events
from app.routers.scans import (
    enforce_captcha,
    enforce_private_lookup_limit,
    is_loopback,
    peer_host,
    rate_limit_ip,
    set_unlisted_headers,
)
from app.scan.upload import UploadRejected
from app.schemas.agent_scan import (
    AgentAggregateStats,
    AgentReplyRequest,
    AgentScanBootstrapRequest,
    AgentScanBootstrapResponse,
    AgentScanCreateRequest,
    AgentScanCreateResponse,
    AgentScanListEnvelope,
    AgentScanReportDetail,
    AgentScanResultV1,
    AgentScanStatusResponse,
)
from app.services.cli_pow import PowDisabled, PowRejected, verify_pow

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agent-scans", tags=["agent-scans"])
# `GET /api/v1/agent-pack/keys` lives off a sibling prefix (not /agent-scans).
pack_keys_router = APIRouter(prefix="/agent-pack", tags=["agent-scans"])

# Statuses past which a pack must NEVER be re-served (the canaries are spent).
_PACK_CLOSED_STATES = frozenset({"submitted", "graded", "published", "aborted"})
# A run is only submittable from these states (else 409 run_not_submittable).
_SUBMITTABLE_STATES = frozenset({"created", "fetched"})
# Terminal graded states - a re-submit of these is an idempotent replay.
_GRADED_STATES = frozenset({"graded", "published"})


async def _parse_submission(request: Request, settings: Settings) -> AgentScanResultV1:
    """Decode + validate the submission: JSON `agent_scan_result.v1`, a JSON
    `{paste_back}` blob, OR a `text/plain` paste-back body. The decoded payload is
    capped at `upload_max_bytes`; paste-back adds the ratio guard."""
    raw = await request.body()
    if len(raw) > settings.upload_max_bytes:
        raise HTTPException(status_code=413, detail={"error": "upload_too_large"})
    content_type = request.headers.get("content-type", "")

    payload: Any
    try:
        if "application/json" in content_type:
            payload = json.loads(raw.decode("utf-8"))
            if isinstance(payload, dict):
                data = cast("dict[str, Any]", payload)
                if "paste_back" in data:
                    payload = json.loads(decode_pasteback(str(data["paste_back"])).decode("utf-8"))
        else:  # text/plain (or anything else) -> paste-back blob
            payload = json.loads(
                decode_pasteback(raw.decode("utf-8", errors="replace")).decode("utf-8")
            )
    except UploadRejected as exc:
        detail: dict[str, object] = {"error": exc.code}
        if exc.reason is not None:
            detail["reason"] = exc.reason
        raise HTTPException(status_code=exc.status, detail=detail) from exc
    except ValueError as exc:  # JSON / decode errors (UnicodeDecodeError is a ValueError)
        raise HTTPException(status_code=422, detail={"error": "invalid_submission"}) from exc

    try:
        return AgentScanResultV1.model_validate(payload)
    except ValidationError as exc:
        # Surface a compact, payload-free error list so a "close" submission is
        # self-correcting (the agent/CLI sees which field + expected shape failed).
        # Only `loc` + `msg` are exposed — NEVER the submitted value (`input`/`ctx`),
        # keeping the no-raw-payload trace invariant (security.md).
        errors = [
            {"field": ".".join(str(p) for p in err["loc"]), "message": err["msg"]}
            for err in exc.errors(include_url=False)
        ][:20]
        raise HTTPException(
            status_code=422,
            detail={"error": "invalid_submission", "errors": errors},
        ) from exc


async def _resolve_component_run(
    session: AsyncSession, component_scan_run_id: UUID | None
) -> UUID | None:
    """Accept a CLI-supplied component scan_run link only if the run actually exists.

    Best-effort hardening (keeps the mint resilient): a dangling / forged id is
    silently ignored (-> None) rather than dropping a broken FK or failing the mint."""
    if component_scan_run_id is None:
        return None
    exists = await session.get(ScanRun, component_scan_run_id)
    return component_scan_run_id if exists is not None else None


def _submit_opted_out(request: Request) -> bool:
    """The submitter declined telemetry (CLI `--no-telemetry` / universal opt-out)."""
    return request.headers.get("x-saferskills-no-telemetry", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }


def _is_live_unlisted(run: AgentRun | None) -> bool:
    """True only for a present, unlisted, unexpired run - else the route 404s
    generically (no existence/expiry oracle). Mirrors `scans._is_live_unlisted`."""
    if run is None or run.visibility != "unlisted":
        return False
    return not (run.expires_at is not None and run.expires_at < datetime.now(UTC))


async def _gate_agent_submission(
    request: Request, session: AsyncSession, *, settings: Settings
) -> None:
    """Human/bot gate for the agent-scan **mint** endpoints (`POST /agent-scans`
    + `/agent-scans/bootstrap`). Loopback-exempt at the call site. PoW path (CLI)
    elif Turnstile (browser) - both count against the dedicated `agent_scan_submit`
    bucket. Verify precedes the rate-limit + the mint. NOT applied to `/submit`,
    which is authorized solely by the single-use run token (like `/abort`)."""
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
        agent_name=resolve_agent_name(body.agent_name),
        runtime=body.runtime,
        visibility=body.visibility,
        component_scan_run_id=await _resolve_component_run(session, body.component_scan_run_id),
        kind_tally=body.kind_tally,
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


async def _bootstrap(
    body: AgentScanBootstrapRequest, request: Request, session: AsyncSession
) -> AgentScanBootstrapResponse:
    """Mint a run + one-time token and render the platform bootstrap prompt.

    Loopback-exempt gate (mirrors `create_run`). The prompt + structured URLs are
    built **absolute** from `public_base_url` (the webapp proxies `/api/*`) so the
    copy/paste agent reaches the API same-origin - `request.base_url` would be the
    internal proxied origin behind Fly. The CLI ignores the structured URLs and
    rebuilds its own from `run_id` + its `api_base`.
    """
    settings = get_settings()
    if body.platform not in bootstrap_mod.PLATFORMS:
        raise HTTPException(status_code=422, detail={"error": "unknown_platform"})
    if not is_loopback(peer_host(request)):
        await _gate_agent_submission(request, session, settings=settings)

    run = await create_agent_run(
        session,
        agent_name=resolve_agent_name(body.agent_name),
        runtime=body.runtime,
        visibility=body.visibility,
        component_scan_run_id=await _resolve_component_run(session, body.component_scan_run_id),
        kind_tally=body.kind_tally,
    )
    token = mint_submit_token(str(run.id))
    await session.commit()

    base = settings.public_base_url.rstrip("/")
    pack_url = f"{base}/api/v1/agent-scans/{run.id}/pack"
    submit_url = f"{base}/api/v1/agent-scans/{run.id}/submit"
    poll_url = f"{base}/api/v1/agent-scans/{run.id}/status"
    try:
        prompt = bootstrap_mod.render(
            body.platform,
            run_id=str(run.id),
            pack_url=pack_url,
            submit_url=submit_url,
            poll_url=poll_url,
            submit_token=token,
            consent=pack_mod.TELEMETRY_NOTICE,
        )
    except bootstrap_mod.UnknownPlatform as exc:  # defence-in-depth (validated above)
        raise HTTPException(status_code=422, detail={"error": "unknown_platform"}) from exc

    return AgentScanBootstrapResponse(
        run_id=run.id,
        prompt=prompt,
        consent_notice=pack_mod.TELEMETRY_NOTICE,
        pack_url=pack_url,
        submit_token=token,
        poll_url=poll_url,
        share_token=run.share_token,
    )


@router.post(
    "/bootstrap", status_code=status.HTTP_201_CREATED, response_model=AgentScanBootstrapResponse
)
async def bootstrap_run(
    body: AgentScanBootstrapRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> AgentScanBootstrapResponse:
    """Mint a run + return the platform-picked bootstrap prompt."""
    return await _bootstrap(body, request, session)


@router.get("/bootstrap", response_model=AgentScanBootstrapResponse)
async def bootstrap_run_get(
    request: Request,
    platform: str,
    agent_name: str | None = None,
    runtime: str = "other",
    visibility: str = "public",
    session: AsyncSession = Depends(get_session),
) -> AgentScanBootstrapResponse:
    """GET convenience for the web picker (same handler as POST)."""
    try:
        body = AgentScanBootstrapRequest(
            platform=platform,  # type: ignore[arg-type]
            agent_name=agent_name,
            runtime=runtime,  # type: ignore[arg-type]
            visibility=visibility,  # type: ignore[arg-type]
        )
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail={"error": "invalid_bootstrap_request"}) from exc
    return await _bootstrap(body, request, session)


@router.get("/{run_id}/pack")
async def get_pack(
    run_id: UUID,
    x_agent_run_token: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Serve the per-run Ed25519-signed pack (token-gated, 410 after submit).

    Token verify is NO-spend (the agent + CLI each pre-flight a fetch). Refuses to
    re-serve once the run is past `fetched` (the canaries are spent -> 410). Archives
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

    # Archive the served bytes (idempotent - a re-fetch derives identical bytes).
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


@router.post("/{run_id}/submit", response_model=AgentScanReportDetail)
async def submit_run(
    run_id: UUID,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> AgentScanReportDetail:
    """Submit `agent_scan_result.v1`, grade it synchronously, return the report.

    NOT human/bot-gated: the intended caller is the AI agent itself (only an
    `X-Agent-Run-Token`, no Turnstile/PoW). Authorization is the single-use run
    token alone (like `/abort` / `/pack` / `/status`); the run it completes was
    already gated + rate-limited at mint, so the gate here would be redundant and
    unsolvable for the agent.

    Ordered: idempotent-replay (already graded -> stored report, BEFORE the token
    spend so a network-retry never 403s on a spent token) -> single-use token spend
    -> state check -> decode/validate -> store raw -> grade off the event loop ->
    persist -> best-effort telemetry -> public projection (+ share_url if unlisted).
    """
    settings = get_settings()
    run = await session.get(AgentRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="not found")

    # Idempotent replay: a retry of an already-graded submit returns the stored
    # report (the single-use token blocks a second *distinct* submit).
    if run.status in _GRADED_STATES:
        findings = await load_findings(session, run_id)
        return await render_agent_report(
            session,
            run,
            findings,
            settings=settings,
            private=run.visibility == "unlisted",
            evidence=None,
        )
    if run.status not in _SUBMITTABLE_STATES:
        raise HTTPException(status_code=409, detail={"error": "run_not_submittable"})

    try:
        await verify_submit_token(request.headers.get("x-agent-run-token"), str(run_id), session)
    except RunTokenError as exc:
        raise HTTPException(status_code=403, detail={"error": "bad_run_token"}) from exc

    result = await _parse_submission(request, settings)
    if result.run_id != str(run_id):
        raise HTTPException(status_code=422, detail={"error": "run_mismatch"})

    await store_evidence(session, run_id, result)
    run.status = "submitted"

    seed = derive_seed(load_master_key(), str(run.id), run.nonce)
    pack = pack_mod.load_pack_source()
    started = time.perf_counter()
    outcome = await asyncio.to_thread(grade, result, run=run, pack=pack, seed=seed)
    latency_ms = int((time.perf_counter() - started) * 1000)

    opted_out = _submit_opted_out(request)
    await persist_grade(session, run, result, outcome, latency_ms=latency_ms, opted_out=opted_out)
    await session.commit()

    # Build the response BEFORE telemetry so a telemetry failure can never corrupt it.
    findings = await load_findings(session, run_id)
    report = await render_agent_report(
        session,
        run,
        findings,
        settings=settings,
        private=run.visibility == "unlisted",
        evidence=None,
    )

    # Best-effort telemetry - NEVER fails the request.
    try:
        await telemetry_mod.capture(
            session, run=run, result=result, outcome=outcome, request=request, opted_out=opted_out
        )
        events.emit_agent_scan_completed(
            tier=cast("events.TierBucket", run.band),
            findings_count=len(outcome.findings),
            runtime=run.runtime,
        )
    except Exception:  # observability must never break the scan
        await session.rollback()
        logger.warning("agent_scan.telemetry_failed", extra={"run_id": str(run_id)})

    return report


@router.post("/{run_id}/abort", status_code=status.HTTP_204_NO_CONTENT)
async def abort_run(
    run_id: UUID,
    x_agent_run_token: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Explicit cancel: mark the run `aborted` + drop any partial evidence (204).

    Token-authed (no spend) - only the submitter holds the run token. A run already
    graded/published is not abortable (409)."""
    run = await session.get(AgentRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="not found")
    try:
        verify_run_token(x_agent_run_token, str(run_id))
    except RunTokenError as exc:
        raise HTTPException(status_code=403, detail={"error": "bad_run_token"}) from exc
    if run.status in _GRADED_STATES:
        raise HTTPException(status_code=409, detail={"error": "run_not_submittable"})
    await session.execute(delete(AgentEvidence).where(AgentEvidence.agent_run_id == run_id))
    await session.execute(update(AgentRun).where(AgentRun.id == run_id).values(status="aborted"))
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


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

    Invalid / expired / deleted / not-unlisted ALL -> generic 404 (no oracle). A
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
    findings = await load_findings(session, run.id)
    evidence_row = await session.get(AgentEvidence, run.id)
    evidence = evidence_row.result_json if evidence_row is not None else None
    return await render_agent_report(
        session, run, findings, settings=get_settings(), private=True, evidence=evidence
    )


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
    findings = await load_findings(session, run.id)
    return await render_agent_report(session, run, findings, settings=get_settings(), private=False)


@router.delete("/r/{token}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_unlisted_run(
    token: str,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Eager self-delete of an unlisted run via the full `delete_agent_run_cascade`
    (the run row + its FK-CASCADE children). Public -> 404."""
    await enforce_private_lookup_limit(request, session)
    run = (
        await session.execute(select(AgentRun).where(AgentRun.share_token == token))
    ).scalar_one_or_none()
    if not _is_live_unlisted(run):
        raise HTTPException(status_code=404, detail="not found")
    assert run is not None
    # Explicit ordered cascade (findings -> telemetry -> evidence -> run). Refuses a
    # public run; the token ledger is keyed by hash and reaped by the expiry sweep,
    # never run-cascaded. Never touches artifact_blobs.
    await delete_agent_run_cascade(session, run.id, allow_public=False)
    await session.commit()
    set_unlisted_headers(response)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/r/{token}/reply", response_model=AgentScanReportDetail)
async def reply_unlisted_run(
    token: str,
    body: AgentReplyRequest,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
) -> AgentScanReportDetail:
    """Attach the capability-token holder's ≤500-char public right-of-reply to the
    run. Token-gated (same `private_lookup` surface as view/promote/
    delete); persisted on the run + rendered read-only on the report. Generic-404 a
    bad/expired token (no oracle). 500-char server-validated by `AgentReplyRequest`."""
    await enforce_private_lookup_limit(request, session)
    run = (
        await session.execute(select(AgentRun).where(AgentRun.share_token == token))
    ).scalar_one_or_none()
    if not _is_live_unlisted(run):
        raise HTTPException(status_code=404, detail="not found")
    assert run is not None
    run.vendor_reply = body.text.strip()
    run.vendor_reply_at = datetime.now(UTC)
    await session.commit()
    await session.refresh(run)
    set_unlisted_headers(response)
    findings = await load_findings(session, run.id)
    return await render_agent_report(
        session, run, findings, settings=get_settings(), private=True, evidence=None
    )


# ── Directory list + aggregate-stats ────────────────────────────────────────────
# These STATIC paths are registered BEFORE the dynamic `/{run_id}` route below, or
# FastAPI would match `aggregate-stats` as a `run_id`.


@router.get("", response_model=AgentScanListEnvelope)
async def list_runs(
    q: str | None = Query(default=None, max_length=200),
    score_min: int | None = Query(default=None, ge=0, le=100),
    score_max: int | None = Query(default=None, ge=0, le=100),
    period: list[str] = Query(default=[]),
    runtime: list[str] = Query(default=[]),
    severity: list[str] = Query(default=[]),
    sort: str = Query(default="newest"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=24, ge=1, le=60),
    session: AsyncSession = Depends(get_session),
) -> AgentScanListEnvelope:
    """Public-only, filterable, sorted, paginated dossier list (the `/agents` grid).

    Hard-filters `visibility='public' AND status IN ('graded','published') AND score
    IS NOT NULL` - never serves an unlisted/ungraded/null-score run."""
    return await directory_mod.list_public_runs(
        session,
        get_settings(),
        q=q,
        score_min=score_min,
        score_max=score_max,
        periods=period,
        runtimes=runtime,
        severities=severity,
        sort=sort if sort in ("newest", "score_asc", "score_desc") else "newest",
        page=page,
        page_size=page_size,
    )


@router.get("/aggregate-stats", response_model=AgentAggregateStats)
async def get_aggregate_stats(
    session: AsyncSession = Depends(get_session),
) -> AgentAggregateStats:
    """Corpus risk-meter feed: gated % + band distribution over the public corpus.

    `pct_with_critical` is null until the corpus reaches `AGENT_CORPUS_GATE_N`
    (the collecting gate). Public-only."""
    return await directory_mod.aggregate_stats(session, get_settings())


@router.get("/{run_id}", response_model=AgentScanReportDetail)
async def get_run(
    run_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> AgentScanReportDetail:
    """Public projection of a run. 404 for unlisted runs (served only via the token
    route). NEVER loads `agent_evidence` - the public report carries no transcript."""
    run = await session.get(AgentRun, run_id)
    if run is None or run.visibility != "public":
        raise HTTPException(status_code=404, detail="not found")
    findings = await load_findings(session, run.id)
    return await render_agent_report(session, run, findings, settings=get_settings(), private=False)


@router.get("/{run_id}/status", response_model=AgentScanStatusResponse)
async def get_run_status(
    run_id: UUID,
    x_agent_run_token: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
) -> AgentScanStatusResponse:
    """Token-authed lightweight poll - the poll target for BOTH public + unlisted
    runs (the `private_lookup` cap is too low for ~120 polls a 3-min scan needs)."""
    run = await session.get(AgentRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="not found")
    try:
        verify_run_token(x_agent_run_token, str(run_id))
    except RunTokenError as exc:
        raise HTTPException(status_code=403, detail={"error": "bad_run_token"}) from exc
    private = run.visibility == "unlisted"
    report_url, share_url = report_urls(run, get_settings(), private=private)
    return AgentScanStatusResponse(
        status=run.status,
        score=run.score,
        band=run.band if run.score is not None else None,
        report_url=report_url,
        share_url=share_url,
    )
