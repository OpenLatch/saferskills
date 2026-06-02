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
from fastapi.responses import RedirectResponse
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
from app.schemas.scan_report_summary import ListEnvelope, ScanReportSummary
from app.schemas.scan_run import PromoteRunResponse, ScanRunReportDetail
from app.schemas.scan_submit import (
    ScanReportDetail,
    ScanSubmitRequest,
    ScanSubmitResponse,
    ScanUploadResponse,
)

logger = logging.getLogger(__name__)

_KINDS = {"skill", "mcp_server", "hook", "plugin", "rules"}

router = APIRouter(prefix="/scans", tags=["scans"])


def _share_url(settings: Settings, token: str | None) -> str | None:
    """Build the public capability URL for a token, or None for public runs."""
    if token is None:
        return None
    return f"{settings.public_base_url.rstrip('/')}/scans/r/{token}"


def _set_unlisted_headers(response: Response) -> None:
    """Anti-leakage headers on a `/scans/r/*` API response (D-UP-32).

    Defense-in-depth ONLY — the browser/crawler/SDK sees the Astro PAGE response,
    which sets the same three headers at page level (the primary protection)."""
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Robots-Tag"] = "noindex, nofollow"
    response.headers["Cache-Control"] = "private, no-store"


# Hold strong references to scan-runner tasks so the GC doesn't collect them
# mid-run (cf. asyncio.create_task docs). Tasks self-remove on completion.
_background_tasks: set[asyncio.Task[None]] = set()


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

    # Public-only feed — unlisted runs never appear in any list (D-UP-19).
    stmt = (
        select(ScanRun, func.coalesce(findings_per_run.c.c, 0).label("findings_count"))
        .join(findings_per_run, findings_per_run.c.run_id == ScanRun.id, isouter=True)
        .where(ScanRun.visibility == "public")
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
        await session.execute(select(func.count(ScanRun.id)).where(ScanRun.visibility == "public"))
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
    try:
        ref = parse_github_url(body.github_url)
    except FetchError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    # The public per-IP daily cap (D-FE-11) is an anti-abuse control for
    # anonymous submissions. Trusted local seeding (the data-seed CLI publishing
    # the fixture corpus) connects over loopback and is exempt — otherwise the
    # ~50-item corpus would blow past the 10/day budget on the first run. See
    # `_is_loopback` for why this never exempts real public traffic.
    ip = request.client.host if request.client else "unknown"
    if not _is_loopback(ip):
        await enforce_ip_rate_limit(
            session,
            ip=ip,
            bucket="scan_submit",
            limit=settings.scan_submit_daily_limit,
        )

    # Resolve a stable idempotency key. We don't know the head SHA until the
    # engine fetches; the key is computed against the URL + rubric only — this
    # is a reasonable tradeoff for Phase B since a rubric-version pin is what
    # vendors expect for a "permanent" report.
    del ref  # validated above; the engine re-parses on the worker side.
    rubric_version = settings.rubric_version or settings.git_sha or "unknown"
    engine_version = settings.engine_version or settings.git_sha or "unknown"
    is_unlisted = body.visibility == "unlisted"

    # Public key stays byte-identical to the pre-I-3.5 form (no nonce), so cached
    # public runs still hit. Unlisted salts with a per-submission nonce AND skips
    # the cache lookup entirely (D-UP-28) — never couple two private submitters.
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
) -> tuple[str, list[bytes], dict[str, str]]:
    """Stream-parse a `multipart/form-data` body, aborting at `max_bytes` BEFORE
    buffering the whole body (D-UP-07 / P1-1).

    ONE concrete path: `request.stream()` fed to python-multipart's `MultipartParser`
    with bounded callbacks. We never call `request.form()` (it spools the part to a
    temp file, buffering past the cap). The file-part tally raises `UploadRejected`
    mid-stream from inside `on_part_data`, which `parser.write()` propagates.
    """
    ctype, opts = parse_options_header(request.headers.get("content-type", ""))
    if ctype != b"multipart/form-data" or b"boundary" not in opts:
        raise UploadRejected(422, "malformed_multipart")
    boundary = opts[b"boundary"]

    fields: dict[str, str] = {}
    file_chunks: list[bytes] = []
    st: dict[str, object] = {
        "total": 0,
        "filename": None,
        "is_file": False,
        "field_name": None,
        "hfield": bytearray(),
        "hvalue": bytearray(),
        "headers": {},
        "fbuf": bytearray(),
    }

    def on_part_begin() -> None:
        st.update(
            is_file=False,
            field_name=None,
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
            st["filename"] = fname.decode("utf-8", "replace")

    def on_part_data(data: bytes, start: int, end: int) -> None:
        chunk = data[start:end]
        if st["is_file"]:
            st["total"] = int(st["total"]) + len(chunk)  # type: ignore[arg-type]
            if int(st["total"]) > max_bytes:  # type: ignore[arg-type]
                raise UploadRejected(413, "upload_too_large")
            file_chunks.append(bytes(chunk))
        elif st["field_name"]:
            st["fbuf"] += chunk  # type: ignore[operator]

    def on_part_end() -> None:
        if not st["is_file"] and st["field_name"]:
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

    if st["filename"] is None:
        raise UploadRejected(422, "malformed_multipart")
    return str(st["filename"]), file_chunks, fields


async def _aiter_chunks(chunks: list[bytes]):
    for c in chunks:
        yield c


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
    """Upload a single capability file or a `.zip` (≤10 MiB) → scan it like a repo.

    The upload is a second front-end to the unchanged engine: extraction yields
    the same in-memory file index a GitHub fetch produces. Shares the `scan_submit`
    per-IP daily bucket (loopback exempt). `visibility` defaults to `public`.
    """
    settings = get_settings()
    ip = request.client.host if request.client else "unknown"
    if not _is_loopback(ip):
        await enforce_ip_rate_limit(
            session, ip=ip, bucket="scan_submit", limit=settings.scan_submit_daily_limit
        )

    try:
        filename, file_chunks, fields = await _read_multipart_upload(
            request, max_bytes=settings.upload_max_bytes
        )
        visibility = fields.get("visibility", "public")
        if visibility not in ("public", "unlisted"):
            raise UploadRejected(422, "invalid_visibility")
        kind_hint = fields.get("kind")
        if kind_hint is not None and kind_hint not in _KINDS:
            raise UploadRejected(422, "invalid_kind")

        extracted: ExtractedUpload = await extract_upload(
            _aiter_chunks(file_chunks), filename, settings=settings
        )
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

    total_bytes = sum(len(c) for c in file_chunks)
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
    generically (no existence/expiry oracle, D-UP-15)."""
    if run is None or run.visibility != "unlisted":
        return False
    return not (run.expires_at is not None and run.expires_at < datetime.now(UTC))


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
    ip = request.client.host if request.client else "unknown"
    if not _is_loopback(ip):
        await enforce_ip_rate_limit(
            session, ip=ip, bucket="private_lookup", limit=settings_private_limit()
        )

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
    _set_unlisted_headers(response)
    return build_scan_run_report(
        run, capabilities, share_url=_share_url(get_settings(), run.share_token)
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
    ip = request.client.host if request.client else "unknown"
    if not _is_loopback(ip):
        await enforce_ip_rate_limit(
            session, ip=ip, bucket="private_lookup", limit=settings_private_limit()
        )

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
    ip = request.client.host if request.client else "unknown"
    if not _is_loopback(ip):
        await enforce_ip_rate_limit(
            session, ip=ip, bucket="private_lookup", limit=settings_private_limit()
        )

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


def settings_private_limit() -> int:
    return get_settings().private_lookup_daily_limit


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
    return build_scan_run_report(run, capabilities)


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

    return build_scan_report_detail(scan, item, findings)


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
