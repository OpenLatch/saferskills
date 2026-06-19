"""Public scans surface — list, submit, repo report, single-capability report, SSE.

A scan targets a GitHub repo; the engine discovers + scores N capabilities and
fans them out under one `scan_runs` row. The endpoints are run-keyed:

- `GET  /api/v1/scans` — list recent repo RUNS (one row per repo scan, not per
  capability), projected to the slim `ScanReportSummary` the feed/catalog use.
- `POST /api/v1/scans` flow:
  1. IP rate-limit check (10/day per `.claude/rules/security.md`; loopback
     callers — trusted local seeding — are exempt).
  2. Compute idempotency key sha256(github_url||0*40||rubric_version).
  3. Cache hit → return the existing run as 200 OK.
  4. Cache miss → insert a pending `scan_runs` row, spawn
     `scan_run_repo(run_id, github_url, rubric_version)` fire-and-forget, return
     202 Accepted with the new run id.
- `GET  /api/v1/scans/runs/<run_id>` — the repo report (all capabilities).
- `GET  /api/v1/scans/<scan_id>` — a single capability's scan report.
- `GET  /api/v1/scans/<run_id>/events` — SSE progress, re-keyed onto the run:
  catch-up replay from `scan_events` (`event_seq > last-event-id`), then LISTEN
  on `scan_progress_<run_id>` via raw asyncpg until status=completed/failed.
"""

from __future__ import annotations

import asyncio
import contextlib
import ipaddress
import json
import logging
import secrets
from datetime import UTC, datetime, timedelta
from typing import Literal, cast
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import RedirectResponse, StreamingResponse
from python_multipart.multipart import MultipartParser, parse_options_header
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from app.core.config import Settings, get_settings
from app.core.db_pool import get_pool
from app.core.rate_limit import enforce_ip_rate_limit
from app.db.session import get_session
from app.models.catalog_item import CatalogItem
from app.models.scan import Finding, Scan, ScanEvent
from app.models.scan_run import ScanRun
from app.observability.events import emit_promote_to_public as _emit_promote
from app.observability.events import emit_scan_submitted, emit_upload_rejected, upload_size_bucket
from app.scan import persistence
from app.scan.fetch import FetchError, parse_github_url
from app.scan.persistence import display_name_for, slug_for
from app.scan.report_builder import build_scan_report_detail, build_scan_run_report
from app.scan.upload import (
    ExtractedUpload,
    UploadRejected,
    extract_upload,
    public_upload_idempotency_key,
    unlisted_idempotency_key,
    upload_content_hash,
)
from app.schemas.item_detail import DownloadInfo, ManifestSource
from app.schemas.scan_report_summary import ListEnvelope, ScanReportSummary
from app.schemas.scan_run import PromoteRunResponse, ScanRunReportDetail
from app.schemas.scan_submit import (
    CliChallengeResponse,
    ScanReportDetail,
    ScanSubmitRequest,
    ScanSubmitResponse,
    ScanUploadResponse,
)
from app.services.artifact_bytes import build_zip, resolve_snapshot, snapshot_byte_size
from app.services.cli_pow import PowDisabled, PowRejected, issue_challenge, verify_pow
from app.services.finding_evidence import resolve_finding_excerpts, resolve_run_evidence
from app.services.turnstile import verify_turnstile

logger = logging.getLogger(__name__)

_KINDS = {"skill", "mcp_server", "hook", "plugin", "rules"}

# Bulk auto-scan run sources kept OUT of the public /scans feed (the firehose the
# durable reconciliation drainer produces). The feed = submissions + drift/appeal.
_FEED_EXCLUDED_SOURCES = ("ingestion", "rescan_rules")

router = APIRouter(prefix="/scans", tags=["scans"])


def _share_url(settings: Settings, token: str | None) -> str | None:
    """Build the public capability URL for a token, or None for public runs."""
    if token is None:
        return None
    return f"{settings.public_base_url.rstrip('/')}/scans/r/{token}"


def _set_unlisted_headers(response: Response) -> None:
    """Anti-leakage headers on a `/scans/r/*` API response.

    Defense-in-depth ONLY — the browser/crawler/SDK sees the Astro PAGE response,
    which sets the same three headers at page level (the primary protection)."""
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Robots-Tag"] = "noindex, nofollow"
    response.headers["Cache-Control"] = "private, no-store"


# Hold strong references to scan-runner tasks so the GC doesn't collect them
# mid-run (cf. asyncio.create_task docs). Tasks self-remove on completion.
_background_tasks: set[asyncio.Task[None]] = set()


async def cancel_background_scans(
    timeout: float,  # noqa: ASYNC109 — bounded-teardown helper (delegates to cancel_and_settle)
) -> None:
    """Cancel the fire-and-forget interactive scan tasks on lifespan shutdown.

    Snapshots `_background_tasks` (the set mutates as tasks self-remove via their
    done-callback), cancels each, and bounded-waits — so an orphaned interactive
    scan never runs on into a dying event loop. No-op when none are in flight.
    """
    tasks = list(_background_tasks)
    if not tasks:
        return
    from app.core.shutdown import cancel_and_settle

    for task in tasks:
        await cancel_and_settle(task, timeout, f"interactive-scan {task.get_name()}")


def _captcha_http_error() -> HTTPException:
    """403 with the bucketed `{"error": ...}` shape the frontend `mapUploadError`
    (`scans.ts`) parses — matches `_upload_http_error` so the gate buckets cleanly."""
    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail={"error": "captcha_failed"})


async def _enforce_captcha(request: Request) -> None:
    """Verify the Turnstile token header before any scan work — 403 on failure.

    Reads the `Cf-Turnstile-Response` custom header (CORS already allows it via
    `allow_headers=["*"]`). Loopback callers (trusted seed) skip this entirely —
    the call sites gate on `_is_loopback`, mirroring the rate-limit exemption.
    Unconfigured (no secret) → `verify_turnstile` returns True, so this is a
    no-op in dev/test/CI. See `app/services/turnstile.py`.
    """
    token = request.headers.get("cf-turnstile-response")
    if not await verify_turnstile(token):
        raise _captcha_http_error()


async def _gate_submission(
    request: Request, session: AsyncSession, *, ip: str, settings: Settings
) -> None:
    """Human/bot gate + per-IP rate limit for BOTH scan-submit endpoints.

    Loopback callers (trusted seed) are exempt and never reach here. Otherwise:

    - **CLI Proof-of-Work path** — an `X-SaferSkills-CLI-PoW` header present AND no
      `Cf-Turnstile-Response` → verify the stateless PoW (the CLI can't solve a
      Turnstile CAPTCHA). Counts against the `cli_scan_submit` bucket.
    - **Browser/Turnstile path** — otherwise verify Turnstile (`scan_submit` bucket).

    Verify ALWAYS precedes the rate-limit (a failed gate never consumes budget) and
    precedes URL-parse / multipart streaming / the idempotency-cache lookup — a
    tokenless bot can neither probe URL validation nor farm a cached public run.
    """
    pow_header = request.headers.get("x-saferskills-cli-pow")
    turnstile_token = request.headers.get("cf-turnstile-response")
    if pow_header and not turnstile_token:
        try:
            await verify_pow(pow_header, session)
        except PowDisabled as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={"error": "pow_unavailable"},
            ) from exc
        except PowRejected as exc:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail={"error": "pow_failed"}
            ) from exc
        await enforce_ip_rate_limit(
            session, ip=ip, bucket="cli_scan_submit", limit=settings.cli_scan_submit_daily_limit
        )
    else:
        await _enforce_captcha(request)
        await enforce_ip_rate_limit(
            session, ip=ip, bucket="scan_submit", limit=settings.scan_submit_daily_limit
        )


def _is_loopback(host: str) -> bool:
    """True if `host` is a loopback address (127.0.0.0/8 or ::1).

    Loopback means the request originated on the API's own machine — the
    trusted maintainer path the data-seed CLI (`catalog publish`) uses to bulk-
    publish the fixture corpus. Public traffic on Fly arrives over the 6PN proxy
    (fdaa::/16) and is never loopback, so this exemption never touches real
    users. `request.client.host` is the actual TCP peer, which a remote client
    cannot spoof to a loopback value.
    """
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _peer_host(request: Request) -> str:
    """The raw TCP peer — the unspoofable basis for the loopback exemption."""
    return request.client.host if request.client else "unknown"


def _rate_limit_ip(request: Request, settings: Settings) -> str:
    """The per-IP rate-limit bucket key.

    Behind the same-origin webapp proxy the TCP peer is the proxy, not the
    visitor, so all callers would share one bucket. The proxy proves itself with
    a shared secret (`X-Proxy-Secret` header == `SAFERSKILLS_PROXY_SHARED_SECRET`);
    on a secret-matched request we trust the left-most `X-Forwarded-For` entry (the
    real visitor the proxy preserved). A direct caller to the public API cannot
    forge the secret, so its spoofed XFF is ignored and it falls back to the real
    peer. No secret configured (dev/test/direct) → the peer. This is the bucket
    key ONLY — the loopback exemption stays on `_peer_host`, so neither a spoofed
    XFF nor a spoofed secret can ever grant the loopback exemption.
    """
    secret = settings.saferskills_proxy_shared_secret
    if secret and secrets.compare_digest(request.headers.get("x-proxy-secret", ""), secret):
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            first = forwarded.split(",")[0].strip()
            if first:
                return first
    return _peer_host(request)


async def _enforce_private_lookup_limit(request: Request, session: AsyncSession) -> None:
    """Loopback-exempt `private_lookup` per-IP cap shared by the four unlisted-run
    token routes (view / promote / delete / download)."""
    if not _is_loopback(_peer_host(request)):
        await enforce_ip_rate_limit(
            session,
            ip=_rate_limit_ip(request, get_settings()),
            bucket="private_lookup",
            limit=settings_private_limit(),
        )


# ── Public re-exports for sibling routers (`agent_scans`) ─────────────────────
# These request-gate + unlisted helpers are the SINGLE SOURCE OF TRUTH for the
# trusted-proxy client-IP, the generic-404 contract, and the anti-leakage headers.
# Exposed under public names so `agent_scans.py` reuses the exact same behaviour
# without a private cross-module import (the internal `_`-prefixed call sites here
# stay unchanged). A change to the security contract updates both surfaces at once.
enforce_captcha = _enforce_captcha
is_loopback = _is_loopback
peer_host = _peer_host
rate_limit_ip = _rate_limit_ip
enforce_private_lookup_limit = _enforce_private_lookup_limit
set_unlisted_headers = _set_unlisted_headers


def _run_summary_row(run: ScanRun, findings_count: int) -> ScanReportSummary:
    """Project a repo scan run → the slim feed/catalog row. slug/author/title are
    derived from the repo URL (github) or the artifact (upload) — a run groups
    several capabilities, so the slug is a label, not a per-capability permalink."""
    if run.source_kind == "upload":
        slug = f"upload--{(run.content_hash_sha256 or '00000000')[:8]}"
        author: str | None = "upload"
        title: str | None = run.original_filename or "Uploaded artifact"
    else:
        slug = run.github_url or "unknown--unknown"
        author = None
        title = None
        try:
            ref = parse_github_url(run.github_url or "")
            slug = slug_for(ref)
            author = ref.org
            title = display_name_for(ref)
        except FetchError:
            pass
    return ScanReportSummary.model_validate(
        {
            "id": str(run.id),
            "github_url": run.github_url,
            "slug": slug,
            "aggregate_score": run.repo_aggregate_score,
            "tier": run.repo_tier,
            "scanned_at": run.scanned_at,
            "findings_count": findings_count,
            "author": author,
            "title": title,
        }
    )


@router.get(
    "",
    response_model=ListEnvelope,
    summary="List recent scans.",
)
async def list_scans(
    source: Literal["submission", "ingestion", "rescan_drift", "rescan_appeal"] | None = Query(
        default=None
    ),
    tier: Literal["green", "yellow", "orange", "red", "unscoped"] | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    order: Literal["created_at_desc", "created_at_asc", "score_desc", "score_asc"] = Query(
        default="created_at_desc"
    ),
    cursor: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
) -> ListEnvelope:
    """Slim summary list of repo scan RUNS (one row per repo scan, not per
    capability — a multi-capability repo would otherwise flood the feed).
    Findings count sums across the run's per-capability scans."""
    findings_per_run = (
        select(Scan.scan_run_id.label("run_id"), func.count(Finding.id).label("c"))
        .join(Finding, Finding.scan_id == Scan.id)
        .group_by(Scan.scan_run_id)
        .subquery()
    )

    # Public-only feed — unlisted runs never appear in any list. The
    # bulk auto-scan firehose (`ingestion` coverage/freshness + `rescan_rules`
    # version re-evals) is excluded too: the feed is submissions + notable scans,
    # not the thousands of background runs the reconciliation drainer produces.
    # Item scores still surface on /items + item pages.
    stmt = (
        select(ScanRun, func.coalesce(findings_per_run.c.c, 0).label("findings_count"))
        .join(findings_per_run, findings_per_run.c.run_id == ScanRun.id, isouter=True)
        .where(ScanRun.visibility == "public")
        .where(ScanRun.source.notin_(_FEED_EXCLUDED_SOURCES))
    )
    if source is not None:
        stmt = stmt.where(ScanRun.source == source)
    if tier is not None:
        stmt = stmt.where(ScanRun.repo_tier == tier)

    if order == "created_at_desc":
        stmt = stmt.order_by(desc(ScanRun.scanned_at), desc(ScanRun.id))
    elif order == "created_at_asc":
        stmt = stmt.order_by(ScanRun.scanned_at, ScanRun.id)
    elif order == "score_desc":
        stmt = stmt.order_by(desc(ScanRun.repo_aggregate_score), desc(ScanRun.scanned_at))
    else:
        stmt = stmt.order_by(ScanRun.repo_aggregate_score, ScanRun.scanned_at)

    stmt = stmt.limit(limit + 1)
    rows = (await session.execute(stmt)).all()
    has_more = len(rows) > limit
    rows = rows[:limit]

    total = (
        await session.execute(
            select(func.count(ScanRun.id))
            .where(ScanRun.visibility == "public")
            .where(ScanRun.source.notin_(_FEED_EXCLUDED_SOURCES))
        )
    ).scalar_one()
    next_cursor = rows[-1][0].id.hex if (has_more and rows) else None

    return ListEnvelope(
        data=[_run_summary_row(run, int(count)) for run, count in rows],
        next_cursor=next_cursor,
        total_count=int(total),
    )


@router.post(
    "",
    response_model=ScanSubmitResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Submit a public GitHub URL for scanning.",
)
async def submit_scan(
    body: ScanSubmitRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> ScanSubmitResponse:
    settings = get_settings()

    # The public per-IP daily cap is an anti-abuse control for
    # anonymous submissions. Trusted local seeding (the data-seed CLI publishing
    # the fixture corpus) connects over loopback and is exempt — otherwise the
    # ~50-item corpus would blow past the 10/day budget on the first run. See
    # `_is_loopback` for why this never exempts real public traffic. The same
    # exemption covers the Turnstile human gate.
    is_loopback = _is_loopback(_peer_host(request))
    ip = _rate_limit_ip(request, settings)

    # Gate (Turnstile OR CLI Proof-of-Work) + per-IP rate limit precede URL parsing
    # AND the idempotency cache: a tokenless bot must not be able to probe the
    # URL-validation oracle or farm a cached public run. Loopback (trusted seed)
    # skips it. See `_gate_submission`.
    if not is_loopback:
        await _gate_submission(request, session, ip=ip, settings=settings)

    try:
        ref = parse_github_url(body.github_url)
    except FetchError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    # Resolve a stable idempotency key. We don't know the head SHA until the
    # engine fetches; the key is computed against the URL + rubric only — this
    # is a reasonable tradeoff since a rubric-version pin is what
    # vendors expect for a "permanent" report.
    del ref  # validated above; the engine re-parses on the worker side.
    rubric_version = settings.rubric_version or settings.git_sha or "unknown"
    engine_version = settings.engine_version or settings.git_sha or "unknown"
    is_unlisted = body.visibility == "unlisted"

    # Public key stays byte-identical to the earlier public-only form (no nonce),
    # so cached public runs still hit. Unlisted salts with a per-submission nonce
    # AND skips the cache lookup entirely — never couple two private submitters.
    if is_unlisted:
        idempotency_key = persistence.compute_idempotency_key(
            body.github_url,
            ref_sha="0" * 40,
            rubric_version=rubric_version,
            nonce=secrets.token_hex(16),
        )
    else:
        idempotency_key = persistence.compute_idempotency_key(
            body.github_url, ref_sha="0" * 40, rubric_version=rubric_version
        )
        if not body.rescan:
            existing = await persistence.select_existing_run_by_idempotency(
                session, idempotency_key
            )
            if existing is not None:
                status_ = "completed" if existing.status == "completed" else "running"
                return ScanSubmitResponse(
                    id=str(existing.id),
                    status=status_,
                    cached=True,
                    rubric_version=existing.rubric_version,
                    submitted_at=existing.scanned_at,
                )

    share_token: str | None = None
    expires_at: datetime | None = None
    if is_unlisted:
        share_token = secrets.token_urlsafe(32)
        expires_at = datetime.now(UTC) + timedelta(days=settings.unlisted_retention_days)

    run = await persistence.persist_pending_scan_run(
        session,
        idempotency_key=idempotency_key,
        github_url=body.github_url,
        rubric_version=rubric_version,
        engine_version=engine_version,
        source="submission",
        visibility=body.visibility,
        source_kind="github",
        share_token=share_token,
        expires_at=expires_at,
    )
    await session.commit()
    emit_scan_submitted(
        source="submission",
        idempotency_cache_hit=False,
        artifact_source="github",
        visibility=body.visibility,
    )

    from app.queue.scan_runner import scan_run_repo

    # Fire-and-forget — the SSE channel `scan_progress_<run_id>` drives the client
    # view. Stash the reference so the GC can't collect it mid-run.
    task = asyncio.create_task(scan_run_repo(run.id, body.github_url, rubric_version))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)

    return ScanSubmitResponse(
        id=str(run.id),
        status="pending",
        cached=False,
        rubric_version=rubric_version,
        submitted_at=run.scanned_at,
        share_url=_share_url(settings, share_token),
    )


async def _read_multipart_upload(
    request: Request, *, max_bytes: int
) -> tuple[list[tuple[str, bytes]], dict[str, str]]:
    """Stream-parse a `multipart/form-data` body, aborting at `max_bytes` BEFORE
    buffering the whole body. Returns one `(filename, bytes)`
    tuple per file part + the non-file form fields.

    ONE concrete path: `request.stream()` fed to python-multipart's `MultipartParser`
    with bounded callbacks. We never call `request.form()` (it spools the part to a
    temp file, buffering past the cap). The cumulative tally (`st["total"]` spans
    ALL file parts) raises `UploadRejected` mid-stream from inside `on_part_data`,
    which `parser.write()` propagates — so the 10 MiB cap is across the batch.
    """
    ctype, opts = parse_options_header(request.headers.get("content-type", ""))
    if ctype != b"multipart/form-data" or b"boundary" not in opts:
        raise UploadRejected(422, "malformed_multipart")
    boundary = opts[b"boundary"]

    fields: dict[str, str] = {}
    file_parts: list[tuple[str, bytes]] = []
    st: dict[str, object] = {
        "total": 0,
        "is_file": False,
        "field_name": None,
        "cur_name": None,
        "cur_buf": bytearray(),
        "hfield": bytearray(),
        "hvalue": bytearray(),
        "headers": {},
        "fbuf": bytearray(),
    }

    def on_part_begin() -> None:
        st.update(
            is_file=False,
            field_name=None,
            cur_name=None,
            cur_buf=bytearray(),
            headers={},
            fbuf=bytearray(),
            hfield=bytearray(),
            hvalue=bytearray(),
        )

    def on_header_field(data: bytes, start: int, end: int) -> None:
        st["hfield"] += data[start:end]  # type: ignore[operator]

    def on_header_value(data: bytes, start: int, end: int) -> None:
        st["hvalue"] += data[start:end]  # type: ignore[operator]

    def on_header_end() -> None:
        name = bytes(st["hfield"]).decode("latin-1").lower()  # type: ignore[arg-type]
        st["headers"][name] = bytes(st["hvalue"]).decode("latin-1")  # type: ignore[index,arg-type]
        st["hfield"] = bytearray()
        st["hvalue"] = bytearray()

    def on_headers_finished() -> None:
        headers = cast("dict[str, str]", st["headers"])
        cd = headers.get("content-disposition", "")
        _, cd_opts = parse_options_header(cd)
        fname = cd_opts.get(b"filename")
        field = cd_opts.get(b"name")
        st["field_name"] = field.decode("latin-1") if field else None
        if fname is not None:
            st["is_file"] = True
            st["cur_name"] = fname.decode("utf-8", "replace")

    def on_part_data(data: bytes, start: int, end: int) -> None:
        chunk = data[start:end]
        if st["is_file"]:
            st["total"] = int(st["total"]) + len(chunk)  # type: ignore[arg-type]
            if int(st["total"]) > max_bytes:  # type: ignore[arg-type]
                raise UploadRejected(413, "upload_too_large")
            st["cur_buf"] += chunk  # type: ignore[operator]
        elif st["field_name"]:
            st["fbuf"] += chunk  # type: ignore[operator]

    def on_part_end() -> None:
        if st["is_file"] and st["cur_name"] is not None:
            file_parts.append((str(st["cur_name"]), bytes(cast("bytearray", st["cur_buf"]))))
        elif st["field_name"]:
            fields[str(st["field_name"])] = bytes(st["fbuf"]).decode("utf-8", "replace").strip()  # type: ignore[arg-type]

    parser = MultipartParser(
        boundary,
        callbacks={
            "on_part_begin": on_part_begin,
            "on_header_field": on_header_field,
            "on_header_value": on_header_value,
            "on_header_end": on_header_end,
            "on_headers_finished": on_headers_finished,
            "on_part_data": on_part_data,
            "on_part_end": on_part_end,
        },
    )
    async for chunk in request.stream():
        parser.write(chunk)
    parser.finalize()

    if not file_parts:
        raise UploadRejected(422, "malformed_multipart")
    return file_parts, fields


@router.post(
    "/upload",
    response_model=ScanUploadResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Submit an uploaded artifact for scanning.",
)
async def submit_upload(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> ScanUploadResponse:
    """Upload one file, one `.zip`, or N loose files (combined ≤10 MiB) → scan it
    like a repo.

    The upload is a second front-end to the unchanged engine: extraction yields
    the same in-memory file index a GitHub fetch produces. Shares the `scan_submit`
    per-IP daily bucket (loopback exempt). `visibility` defaults to `public`.
    """
    settings = get_settings()
    is_loopback = _is_loopback(_peer_host(request))
    ip = _rate_limit_ip(request, settings)

    # Verify the gate (Turnstile OR CLI Proof-of-Work) + rate limit BEFORE
    # streaming/parsing the multipart body — reject a bot before we spend
    # bandwidth/CPU on the parse. Loopback (trusted seed) skips. See `_gate_submission`.
    if not is_loopback:
        await _gate_submission(request, session, ip=ip, settings=settings)

    try:
        parts, fields = await _read_multipart_upload(request, max_bytes=settings.upload_max_bytes)
        visibility = fields.get("visibility", "public")
        if visibility not in ("public", "unlisted"):
            raise UploadRejected(422, "invalid_visibility")
        kind_hint = fields.get("kind")
        if kind_hint is not None and kind_hint not in _KINDS:
            raise UploadRejected(422, "invalid_kind")

        extracted: ExtractedUpload = extract_upload(parts, settings=settings)
    except UploadRejected as exc:
        _emit_upload_rejected(exc)
        raise _upload_http_error(exc) from exc

    content_hash = upload_content_hash(extracted.files_index)
    rubric_version = settings.rubric_version or settings.git_sha or "unknown"
    engine_version = settings.engine_version or settings.git_sha or "unknown"
    is_unlisted = visibility == "unlisted"

    if is_unlisted:
        idempotency_key = unlisted_idempotency_key(content_hash, rubric_version)
    else:
        idempotency_key = public_upload_idempotency_key(content_hash, rubric_version)
        existing = await persistence.select_existing_run_by_idempotency(session, idempotency_key)
        if existing is not None:
            return ScanUploadResponse(
                id=str(existing.id),
                status="completed" if existing.status == "completed" else "running",
                source_kind="upload",
                visibility="public",
                slug=None,
                share_url=None,
            )

    share_token: str | None = None
    expires_at: datetime | None = None
    if is_unlisted:
        share_token = secrets.token_urlsafe(32)
        expires_at = datetime.now(UTC) + timedelta(days=settings.unlisted_retention_days)

    run = await persistence.persist_pending_scan_run(
        session,
        idempotency_key=idempotency_key,
        github_url=None,
        rubric_version=rubric_version,
        engine_version=engine_version,
        source="submission",
        visibility=visibility,
        source_kind="upload",
        share_token=share_token,
        expires_at=expires_at,
        original_filename=extracted.original_filename,
        content_hash_sha256=content_hash,
    )
    await session.commit()

    total_bytes = sum(len(b) for _, b in parts)
    emit_scan_submitted(
        source="submission",
        idempotency_cache_hit=False,
        artifact_source="upload",
        visibility=visibility,
        upload_size_bucket=upload_size_bucket(total_bytes),
    )

    from app.queue.scan_runner import scan_run_upload

    task = asyncio.create_task(scan_run_upload(run.id, extracted.files_index, rubric_version))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)

    return ScanUploadResponse(
        id=str(run.id),
        status="pending",
        source_kind="upload",
        visibility=visibility,  # type: ignore[arg-type]
        slug=None,  # known once the run completes; the FE polls the run report
        share_url=_share_url(settings, share_token),
    )


def _upload_http_error(exc: UploadRejected) -> HTTPException:
    detail: dict[str, object] = {"error": exc.code}
    if exc.reason is not None:
        detail["reason"] = exc.reason
    return HTTPException(status_code=exc.status, detail=detail)


def _emit_upload_rejected(exc: UploadRejected) -> None:
    reason_map = {
        "upload_too_large": "too_big",
        "unsupported_type": "bad_type",
        "binary_not_allowed": "binary",
        "archive_rejected": "archive_rejected",
    }
    reason = reason_map.get(exc.code)
    if reason is None:
        return
    emit_upload_rejected(reason=reason, archive_sub=exc.reason)  # type: ignore[arg-type]


async def _load_run_capabilities(
    session: AsyncSession, run_id: UUID
) -> list[tuple[Scan, CatalogItem, list[Finding]]]:
    """`(scan, catalog_item, findings)` per discovered capability of a run,
    ordered by (kind, display_name) — shared by the run report + token view."""
    rows = (
        await session.execute(
            select(Scan, CatalogItem)
            .join(CatalogItem, CatalogItem.id == Scan.catalog_item_id)
            .where(Scan.scan_run_id == run_id)
            .order_by(CatalogItem.kind, CatalogItem.display_name)
        )
    ).all()
    scan_ids = [scan.id for scan, _ in rows]
    findings_by_scan: dict[UUID, list[Finding]] = {}
    if scan_ids:
        all_findings = (
            (await session.execute(select(Finding).where(Finding.scan_id.in_(scan_ids))))
            .scalars()
            .all()
        )
        for f in all_findings:
            findings_by_scan.setdefault(f.scan_id, []).append(f)
    return [(scan, item, findings_by_scan.get(scan.id, [])) for scan, item in rows]


def _is_live_unlisted(run: ScanRun | None) -> bool:
    """True only for a present, unlisted, unexpired run — else the route 404s
    generically (no existence/expiry oracle)."""
    if run is None or run.visibility != "unlisted":
        return False
    return not (run.expires_at is not None and run.expires_at < datetime.now(UTC))


async def _capability_extras(
    session: AsyncSession, scan: Scan
) -> tuple[ManifestSource | None, DownloadInfo | None]:
    """Primary manifest + `.zip` pointer for ONE capability scan — the rich-report
    Source viewer + download. Carried per-capability so a multi-file upload renders
    one rich report per file. The bytes come from the storage-split
    resolver, so this works for public uploads (`artifact_blobs`) and unlisted
    uploads (`upload_files`) alike."""
    manifest: ManifestSource | None = None
    if scan.manifest_source:
        manifest = ManifestSource(
            path=scan.manifest_path or "SKILL.md",
            content=scan.manifest_source,
            bytes=len(scan.manifest_source.encode("utf-8")),
        )
    download: DownloadInfo | None = None
    if scan.file_hashes:
        size = await snapshot_byte_size(session, scan)
        if size > 0:
            download = DownloadInfo(scan_id=str(scan.id), byte_size=size)
    return manifest, download


async def _run_capability_extras(
    session: AsyncSession,
    capabilities: list[tuple[Scan, CatalogItem, list[Finding]]],
) -> tuple[
    dict[str, tuple[ManifestSource | None, DownloadInfo | None]],
    ManifestSource | None,
    DownloadInfo | None,
]:
    """Per-capability extras map + the single-capability run-level (manifest,
    download). The run-level pair is kept ONLY for a single-capability run (the
    rich single-file upload report); multi-file uploads read each capability's own
    extras off its `CapabilityRow`."""
    extras: dict[str, tuple[ManifestSource | None, DownloadInfo | None]] = {}
    for scan, _item, _findings in capabilities:
        extras[str(scan.id)] = await _capability_extras(session, scan)
    if len(capabilities) == 1:
        manifest, download = extras[str(capabilities[0][0].id)]
    else:
        manifest, download = None, None
    return extras, manifest, download


@router.get(
    "/r/{token}",
    response_model=ScanRunReportDetail,
    summary="Read an unlisted scan report by its capability-URL token.",
)
async def get_unlisted_run(
    token: str,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
) -> ScanRunReportDetail | Response:
    """View an unlisted run via its share token. Invalid / expired / deleted /
    not-unlisted ALL → generic 404 (no oracle). A promoted (now public) run
    307-redirects to the run report."""
    await _enforce_private_lookup_limit(request, session)

    run = (
        await session.execute(select(ScanRun).where(ScanRun.share_token == token))
    ).scalar_one_or_none()

    # A promoted run is public now — redirect to its run report (the page issues
    # the browser-facing Astro.redirect). Keep the token resolvable.
    if run is not None and run.visibility == "public":
        return RedirectResponse(
            url=f"/api/v1/scans/runs/{run.id}", status_code=status.HTTP_307_TEMPORARY_REDIRECT
        )
    if not _is_live_unlisted(run):
        raise HTTPException(status_code=404, detail="not found")
    assert run is not None

    capabilities = await _load_run_capabilities(session, run.id)
    extras, manifest, download = await _run_capability_extras(session, capabilities)
    evidence = await resolve_run_evidence(session, capabilities)
    _set_unlisted_headers(response)
    return build_scan_run_report(
        run,
        capabilities,
        share_url=_share_url(get_settings(), run.share_token),
        manifest=manifest,
        download=download,
        capability_extras=extras,
        evidence=evidence,
    )


@router.post(
    "/r/{token}/promote",
    response_model=PromoteRunResponse,
    summary="Promote an unlisted run to public (one-way).",
)
async def promote_unlisted_run(
    token: str,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
) -> PromoteRunResponse:
    """Promote unlisted → public, one-way. Returns a structured 200 (never a 301).
    Idempotent: an already-public run returns `promoted=False`."""
    await _enforce_private_lookup_limit(request, session)

    run = (
        await session.execute(select(ScanRun).where(ScanRun.share_token == token))
    ).scalar_one_or_none()
    # Allow promote when already public (idempotent no-op); else require live unlisted.
    if run is None or (run.visibility != "public" and not _is_live_unlisted(run)):
        raise HTTPException(status_code=404, detail="not found")

    promoted, items = await persistence.promote_run_to_public(session, run)
    await session.commit()
    _set_unlisted_headers(response)
    if promoted:
        for item in items:
            _emit_promote(catalog_item_id=item["slug"])
    return PromoteRunResponse(
        promoted=promoted,
        run_id=str(run.id),
        visibility="public",
        items=items,  # type: ignore[arg-type]
    )


@router.delete(
    "/r/{token}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an unlisted run by its capability-URL token.",
)
async def delete_unlisted_run(
    token: str,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Delete an unlisted run + everything it owns (ordered cascade). Only
    unlisted runs are token-deletable (public → generic 404). Token → 404."""
    await _enforce_private_lookup_limit(request, session)

    run = (
        await session.execute(select(ScanRun).where(ScanRun.share_token == token))
    ).scalar_one_or_none()
    if not _is_live_unlisted(run):
        raise HTTPException(status_code=404, detail="not found")
    assert run is not None

    await persistence.delete_run_cascade(session, run.id, allow_public=False)
    await session.commit()
    _set_unlisted_headers(response)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


_MAX_ZIP_BYTES = 25 * 1024 * 1024


@router.get(
    "/r/{token}/download",
    summary="Download the scanned bytes (.zip) of an unlisted run by its token.",
)
async def download_unlisted_run(
    token: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> StreamingResponse:
    """Token-gated `.zip` of an unlisted run's scanned bytes (mockups 4 keep the
    download). Same generic-404 / `private_lookup` cap / anti-leakage contract as
    the view route — the public `/items/<slug>/download` 404s for shadow rows, so
    unlisted bytes are reachable only here. Bytes come from the storage-split
    resolver (`upload_files` for unlisted uploads)."""
    await _enforce_private_lookup_limit(request, session)

    run = (
        await session.execute(select(ScanRun).where(ScanRun.share_token == token))
    ).scalar_one_or_none()
    if not _is_live_unlisted(run):
        raise HTTPException(status_code=404, detail="not found")
    assert run is not None

    capabilities = await _load_run_capabilities(session, run.id)
    files: dict[str, bytes] = {}
    for scan, _item, _findings in capabilities:
        snapshot = await resolve_snapshot(session, scan)
        for path, content in snapshot.items():
            if content is not None:
                files[path] = content
    if not files:
        raise HTTPException(status_code=404, detail="not found")

    total = sum(len(b) for b in files.values())
    if total > _MAX_ZIP_BYTES:
        raise HTTPException(status_code=413, detail="snapshot exceeds the download cap")

    payload = await asyncio.to_thread(build_zip, files)
    filename = run.original_filename or "artifact"
    if not filename.endswith(".zip"):
        filename = f"{filename.rsplit('.', 1)[0]}.zip" if "." in filename else f"{filename}.zip"
    headers = {
        "Content-Disposition": f'attachment; filename="{filename}"',
        # Anti-leakage parity with the view route — never cache a token URL.
        "Referrer-Policy": "no-referrer",
        "X-Robots-Tag": "noindex, nofollow",
        "Cache-Control": "private, no-store",
    }
    return StreamingResponse(iter([payload]), media_type="application/zip", headers=headers)


def settings_private_limit() -> int:
    return get_settings().private_lookup_daily_limit


@router.get(
    "/cli-challenge",
    response_model=CliChallengeResponse,
    summary="Issue a stateless Proof-of-Work challenge for the install CLI.",
)
async def cli_challenge() -> CliChallengeResponse:
    """Mint a fresh signed PoW challenge for the install CLI. Declared
    BEFORE the greedy `/{scan_id}` route so the literal path wins. 503 when the
    PoW secret is unconfigured (dev/test/CI — the CLI then falls back to Turnstile).
    """
    try:
        challenge, difficulty, expires_at = issue_challenge()
    except PowDisabled as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"error": "pow_unavailable"},
        ) from exc
    return CliChallengeResponse(challenge=challenge, difficulty=difficulty, expires_at=expires_at)


@router.get(
    "/runs/{run_id}",
    response_model=ScanRunReportDetail,
    summary="Read the full repo scan report (all discovered capabilities) for a run ID.",
)
async def get_scan_run(
    run_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> ScanRunReportDetail:
    """The repo scan surface: consolidated repo score + by-kind tally + one row
    per discovered capability (each its own catalog item) with its findings."""
    run = (await session.execute(select(ScanRun).where(ScanRun.id == run_id))).scalar_one_or_none()
    if run is None:
        raise HTTPException(status_code=404, detail="scan run not found")

    capabilities = await _load_run_capabilities(session, run_id)
    extras, manifest, download = await _run_capability_extras(session, capabilities)
    evidence = await resolve_run_evidence(session, capabilities)
    return build_scan_run_report(
        run,
        capabilities,
        manifest=manifest,
        download=download,
        capability_extras=extras,
        evidence=evidence,
    )


@router.get(
    "/{scan_id}",
    response_model=ScanReportDetail,
    summary="Read the full scan report for a single capability scan ID.",
)
async def get_scan(
    scan_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> ScanReportDetail:
    stmt = (
        select(Scan, CatalogItem)
        .join(CatalogItem, CatalogItem.id == Scan.catalog_item_id)
        .where(Scan.id == scan_id)
    )
    row = (await session.execute(stmt)).first()
    if row is None:
        raise HTTPException(status_code=404, detail="scan not found")
    scan, item = row

    findings_stmt = select(Finding).where(Finding.scan_id == scan_id)
    findings = (await session.execute(findings_stmt)).scalars().all()

    evidence = await resolve_finding_excerpts(session, scan, findings)
    return build_scan_report_detail(scan, item, findings, evidence=evidence)


@router.get(
    "/{run_id}/events",
    summary="SSE progress stream for a repo scan run.",
)
async def scan_events(run_id: UUID, request: Request) -> EventSourceResponse:
    """Server-Sent Events stream of repo-scan progress (re-keyed onto the run).

    Wire format: each event is `{event_seq, stage, completion_pct, status,
    payload, timestamp}` JSON. Clients pass `Last-Event-ID: <run_id>-<seq>`
    to resume — we replay `scan_events` rows for the run whose `event_seq > seq`,
    then subscribe to LISTEN on `scan_progress_<run_id>` for live deltas.
    """
    from app.db.session import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        run = (
            await session.execute(select(ScanRun).where(ScanRun.id == run_id))
        ).scalar_one_or_none()
        if run is None:
            raise HTTPException(404, "scan run not found")

    last_event_id = request.headers.get("last-event-id", "")
    last_event_seq = 0
    if last_event_id and "-" in last_event_id:
        with contextlib.suppress(ValueError):
            last_event_seq = int(last_event_id.split("-")[-1])

    async def event_generator():
        async with AsyncSessionLocal() as catchup_session:
            history_stmt = (
                select(ScanEvent)
                .where(ScanEvent.scan_run_id == run_id)
                .where(ScanEvent.event_seq > last_event_seq)
                .order_by(ScanEvent.event_seq.asc())
            )
            history = (await catchup_session.execute(history_stmt)).scalars().all()

        terminal_seen = False
        for row in history:
            yield {
                "id": f"{run_id}-{row.event_seq}",
                "event": "progress",
                "data": json.dumps(
                    {
                        "event_seq": row.event_seq,
                        "stage": row.stage,
                        "completion_pct": row.completion_pct,
                        "status": row.status,
                        "payload": row.payload or {},
                        "timestamp": row.emitted_at.isoformat() if row.emitted_at else None,
                    }
                ),
            }
            if row.stage == "done" or row.status in ("completed", "failed"):
                terminal_seen = row.stage == "done"

        if terminal_seen:
            return

        # Subscribe to live deltas via asyncpg LISTEN/NOTIFY.
        try:
            pool = get_pool()
        except RuntimeError:
            return

        channel = f"scan_progress_{run_id.hex}"
        queue: asyncio.Queue[str] = asyncio.Queue()

        def _listener(conn: asyncpg.Connection, _pid: int, _channel: str, payload: str) -> None:
            del conn
            queue.put_nowait(payload)

        async with pool.acquire() as conn:  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
            await conn.add_listener(channel, _listener)  # pyright: ignore[reportUnknownMemberType]
            try:
                while True:
                    if await request.is_disconnected():
                        break
                    try:
                        payload = await asyncio.wait_for(queue.get(), timeout=15.0)
                    except TimeoutError:
                        yield {"event": "heartbeat", "data": "{}"}
                        continue
                    data = json.loads(payload)
                    yield {
                        "id": f"{run_id}-{data.get('event_seq', 0)}",
                        "event": "progress",
                        "data": payload,
                    }
                    if data.get("stage") == "done":
                        return
            finally:
                try:
                    await conn.remove_listener(channel, _listener)  # pyright: ignore[reportUnknownMemberType]
                except Exception:
                    logger.exception("failed to remove LISTEN handler for %s", channel)

    return EventSourceResponse(event_generator(), ping=15)
