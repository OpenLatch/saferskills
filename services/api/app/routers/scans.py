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
from typing import Literal
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from app.core.config import get_settings
from app.core.db_pool import get_pool
from app.core.rate_limit import enforce_ip_rate_limit
from app.db.session import get_session
from app.models.catalog_item import CatalogItem
from app.models.scan import Finding, Scan, ScanEvent
from app.models.scan_run import ScanRun
from app.scan import persistence
from app.scan.fetch import FetchError, parse_github_url
from app.scan.persistence import display_name_for, slug_for
from app.scan.report_builder import build_scan_report_detail, build_scan_run_report
from app.schemas.scan_report_summary import ListEnvelope, ScanReportSummary
from app.schemas.scan_run import ScanRunReportDetail
from app.schemas.scan_submit import (
    ScanReportDetail,
    ScanSubmitRequest,
    ScanSubmitResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/scans", tags=["scans"])

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
    derived from the repo URL (a run groups several capabilities — no single
    catalog slug), keeping the 2-segment `<org>--<repo>` summary contract."""
    slug = run.github_url
    author: str | None = None
    title: str | None = None
    try:
        ref = parse_github_url(run.github_url)
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

    stmt = select(ScanRun, func.coalesce(findings_per_run.c.c, 0).label("findings_count")).join(
        findings_per_run, findings_per_run.c.run_id == ScanRun.id, isouter=True
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

    total = (await session.execute(select(func.count(ScanRun.id)))).scalar_one()
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
    idempotency_key = persistence.compute_idempotency_key(
        body.github_url, ref_sha="0" * 40, rubric_version=rubric_version
    )

    if not body.rescan:
        existing = await persistence.select_existing_run_by_idempotency(session, idempotency_key)
        if existing is not None:
            status_ = "completed" if existing.status == "completed" else "running"
            return ScanSubmitResponse(
                id=str(existing.id),
                status=status_,
                cached=True,
                rubric_version=existing.rubric_version,
                submitted_at=existing.scanned_at,
            )

    run = await persistence.persist_pending_scan_run(
        session,
        idempotency_key=idempotency_key,
        github_url=body.github_url,
        rubric_version=rubric_version,
        engine_version=engine_version,
        source="submission",
    )
    await session.commit()

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
    )


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

    capabilities = [(scan, item, findings_by_scan.get(scan.id, [])) for scan, item in rows]
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
