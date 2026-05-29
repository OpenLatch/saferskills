"""Public scans surface — list, submit, detail, SSE progress.

Replaces the W1 `routers/scans_stub.py`. The list endpoint joins `scans` +
`catalog_items` and returns the slim `ScanReportSummary` projection the
homepage feed and catalog row UI consume.

POST `/api/v1/scans` flow:
1. IP rate-limit check (10/day per `.claude/rules/security.md` § Public-input;
   loopback callers — trusted local seeding — are exempt).
2. Compute idempotency key sha256(github_url||ref_sha||rubric_version).
3. Cache hit → return the existing scan as 200 OK.
4. Cache miss → upsert `catalog_items`, insert pending `scans` row, spawn
   `scan_run(scan_id, github_url, rubric_version)` as a fire-and-forget task,
   return 202 Accepted with the new scan_id.

GET `/api/v1/scans/<id>/events`:
- Server-Sent Events stream. Catch-up replay from `scan_events` (everything
  with `event_seq > last-event-id`), then subscribe to `LISTEN
  scan_progress_<id>` via raw asyncpg until status=completed/failed.
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
from app.scan import persistence
from app.scan.fetch import FetchError, parse_github_url
from app.scan.report_builder import build_scan_report_detail
from app.schemas.scan_report_summary import ListEnvelope, ScanReportSummary
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


def _summary_row(scan: Scan, item: CatalogItem | None, findings_count: int) -> ScanReportSummary:
    slug = item.slug if item is not None else scan.github_url
    title = item.display_name if item is not None else None
    author = item.github_org if item is not None else None
    return ScanReportSummary.model_validate(
        {
            "id": str(scan.id),
            "github_url": scan.github_url,
            "slug": slug,
            "aggregate_score": scan.aggregate_score,
            "tier": scan.tier,
            "scanned_at": scan.scanned_at,
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
    """Slim summary list — JOINs scans + catalog_items, projects ScanReportSummary."""
    findings_count = (
        select(Finding.scan_id, func.count(Finding.id).label("c"))
        .group_by(Finding.scan_id)
        .subquery()
    )

    stmt = (
        select(Scan, CatalogItem, func.coalesce(findings_count.c.c, 0).label("findings_count"))
        .join(CatalogItem, CatalogItem.id == Scan.catalog_item_id)
        .join(findings_count, findings_count.c.scan_id == Scan.id, isouter=True)
    )
    if source is not None:
        stmt = stmt.where(Scan.source == source)
    if tier is not None:
        stmt = stmt.where(Scan.tier == tier)

    if order == "created_at_desc":
        stmt = stmt.order_by(desc(Scan.scanned_at), desc(Scan.id))
    elif order == "created_at_asc":
        stmt = stmt.order_by(Scan.scanned_at, Scan.id)
    elif order == "score_desc":
        stmt = stmt.order_by(desc(Scan.aggregate_score), desc(Scan.scanned_at))
    else:
        stmt = stmt.order_by(Scan.aggregate_score, Scan.scanned_at)

    stmt = stmt.limit(limit + 1)
    rows = (await session.execute(stmt)).all()
    has_more = len(rows) > limit
    rows = rows[:limit]

    total = (await session.execute(select(func.count(Scan.id)))).scalar_one()
    next_cursor = rows[-1][0].id.hex if (has_more and rows) else None

    return ListEnvelope(
        data=[_summary_row(scan, item, int(count)) for scan, item, count in rows],
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
    rubric_version = settings.rubric_version or settings.git_sha or "unknown"
    engine_version = settings.engine_version or settings.git_sha or "unknown"
    idempotency_key = persistence.compute_idempotency_key(
        body.github_url, ref_sha="0" * 40, rubric_version=rubric_version
    )

    if not body.rescan:
        existing = await persistence.select_existing_by_idempotency(session, idempotency_key)
        if existing is not None:
            return ScanSubmitResponse(
                id=str(existing.id),
                status="completed" if existing.aggregate_score > 0 else "running",
                cached=True,
                rubric_version=existing.rubric_version,
                submitted_at=existing.scanned_at,
            )

    item = await persistence.ensure_catalog_item(session, ref, body.github_url)
    scan = await persistence.persist_pending_scan(
        session,
        catalog_item_id=item.id,
        idempotency_key=idempotency_key,
        github_url=body.github_url,
        rubric_version=rubric_version,
        engine_version=engine_version,
        source="submission",
    )
    await session.commit()

    from app.queue.scan_runner import scan_run

    # The task is fire-and-forget — the SSE channel drives the client view.
    # We stash the reference on app state so the GC can't collect it mid-run;
    # cleanup happens in lifespan shutdown.
    task = asyncio.create_task(scan_run(scan.id, body.github_url, rubric_version))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)

    return ScanSubmitResponse(
        id=str(scan.id),
        status="pending",
        cached=False,
        rubric_version=rubric_version,
        submitted_at=scan.scanned_at,
    )


@router.get(
    "/{scan_id}",
    response_model=ScanReportDetail,
    summary="Read the full scan report for a given scan ID.",
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
    "/{scan_id}/events",
    summary="SSE progress stream for a scan.",
)
async def scan_events(scan_id: UUID, request: Request) -> EventSourceResponse:
    """Server-Sent Events stream of scan progress.

    Wire format: each event is `{event_seq, stage, completion_pct, status,
    payload, timestamp}` JSON. Clients pass `Last-Event-ID: <scan_id>-<seq>`
    to resume — we replay rows from `scan_events` whose `event_seq > seq`,
    then subscribe to LISTEN for live deltas.
    """
    from app.db.session import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        scan = (await session.execute(select(Scan).where(Scan.id == scan_id))).scalar_one_or_none()
        if scan is None:
            raise HTTPException(404, "scan not found")

    last_event_id = request.headers.get("last-event-id", "")
    last_event_seq = 0
    if last_event_id and "-" in last_event_id:
        with contextlib.suppress(ValueError):
            last_event_seq = int(last_event_id.split("-")[-1])

    async def event_generator():
        async with AsyncSessionLocal() as catchup_session:
            history_stmt = (
                select(ScanEvent)
                .where(ScanEvent.scan_id == scan_id)
                .where(ScanEvent.event_seq > last_event_seq)
                .order_by(ScanEvent.event_seq.asc())
            )
            history = (await catchup_session.execute(history_stmt)).scalars().all()

        terminal_seen = False
        for row in history:
            yield {
                "id": f"{scan_id}-{row.event_seq}",
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

        channel = f"scan_progress_{scan_id.hex}"
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
                        "id": f"{scan_id}-{data.get('event_seq', 0)}",
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
