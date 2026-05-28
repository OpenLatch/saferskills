"""Per-scan async worker. Drives a single scan through every stage.

Stages (matches D-FE-09 + the frontend ScanProgressBoard contract):

    fetch → index → security → supply_chain → maintenance → transparency
         → community → score → sign → done

The worker:
- Inserts a `scan_events` row at each stage boundary (via AsyncSession).
- `pg_notify`'s the same payload on channel `scan_progress_<id>` so live SSE
  consumers receive deltas without polling the table.

`emit()` opens a fresh asyncpg connection from the shared pool for the NOTIFY
half; the AsyncSession is per-emit so each event is a separate small commit
(no long-held transactions during the multi-second scan run).
"""

from __future__ import annotations

import json
import logging
import traceback
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db_pool import get_pool
from app.db.session import AsyncSessionLocal
from app.models.scan import Scan, ScanEvent
from app.scan import engine, persistence

logger = logging.getLogger(__name__)


STAGES_SCORING = ("security", "supply_chain", "maintenance", "transparency", "community")


async def _next_event_seq(session: AsyncSession, scan_id: UUID) -> int:
    max_seq = (
        await session.execute(
            select(func.coalesce(func.max(ScanEvent.event_seq), 0)).where(
                ScanEvent.scan_id == scan_id
            )
        )
    ).scalar_one()
    return int(max_seq) + 1


async def _emit(
    scan_id: UUID,
    stage: str,
    completion_pct: int,
    status: str,
    payload: dict[str, Any] | None = None,
) -> None:
    """Append a scan_events row + NOTIFY listening SSE consumers."""
    async with AsyncSessionLocal() as session:
        event_seq = await _next_event_seq(session, scan_id)
        event = ScanEvent(
            scan_id=scan_id,
            event_seq=event_seq,
            stage=stage,
            completion_pct=completion_pct,
            status=status,
            payload=payload or {},
        )
        session.add(event)
        await session.commit()

    pool = get_pool()
    channel = f"scan_progress_{scan_id.hex}"
    payload_json = json.dumps(
        {
            "event_seq": event_seq,
            "stage": stage,
            "completion_pct": completion_pct,
            "status": status,
            "payload": payload or {},
        }
    )
    async with pool.acquire() as conn:  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
        await conn.execute("SELECT pg_notify($1, $2)", channel, payload_json)  # pyright: ignore[reportUnknownMemberType]


async def scan_run(
    scan_id: UUID,
    github_url: str,
    rubric_version: str,
) -> None:
    """Drive one scan to completion. Emits progress events at each stage.

    Always runs to a terminal state: either `done` (with all sub-scores
    committed) or `failed` (with the exception class in the payload). Caller
    spawns via `asyncio.create_task` from POST /scans and never awaits it.
    """
    try:
        await _emit(scan_id, "fetch", 5, "running", {"target": github_url})

        # The engine runs fetch + walk + ALL rule evaluation + aggregation in one
        # step (it's CPU-bound regex work that doesn't yield meaningful per-stage
        # checkpoints). We post-hoc emit per-stage events so the SSE consumer
        # sees the canonical 10-stage progress shape the frontend expects.
        result = await engine.run_scan(github_url, rubric_version)

        await _emit(
            scan_id,
            "fetch",
            15,
            "completed",
            {"file_count": result.file_count, "ref_sha": result.ref_sha},
        )

        await _emit(
            scan_id,
            "index",
            25,
            "completed",
            {"file_count": result.file_count},
        )

        for sub_score, target_pct in zip(STAGES_SCORING, (50, 65, 75, 85, 90), strict=True):
            count = sum(1 for f in result.findings if f.sub_score == sub_score)
            await _emit(
                scan_id,
                sub_score,
                target_pct,
                "completed",
                {
                    "findings_count": count,
                    "sub_score": result.sub_scores.get(sub_score, 100),
                },
            )

        await _emit(
            scan_id,
            "score",
            98,
            "completed",
            {
                "aggregate_score": result.aggregate_score,
                "tier": result.tier,
            },
        )

        # Persist the final scan + findings.
        async with AsyncSessionLocal() as session:
            cached_scan = (
                await session.execute(select(Scan).where(Scan.id == scan_id))
            ).scalar_one_or_none()
            if cached_scan is None:
                logger.warning("scan_id %s vanished mid-run; skipping commit", scan_id)
            else:
                await persistence.persist_completed_scan(session, cached_scan, result)
                await session.commit()

        await _emit(scan_id, "sign", 100, "completed")
        await _emit(scan_id, "done", 100, "completed")

    except Exception as exc:
        logger.exception("scan %s failed", scan_id)
        try:
            await _emit(
                scan_id,
                "done",
                100,
                "failed",
                {
                    "error_class": type(exc).__name__,
                    "error_message": str(exc),
                    "traceback_tail": traceback.format_exc(limit=3),
                },
            )
        except Exception:
            # Best-effort — emit may itself fail if the pool is down.
            logger.exception("scan %s final emit also failed", scan_id)


async def recover_stale_scans() -> None:
    """Startup hook: re-enqueue any scan whose status is `pending` or whose last
    progress event is older than 5 min and not in a terminal state.

    Stub implementation in Phase B — the engine is in-process so a server restart
    drops the scan; we do NOT auto-restart it because that risks duplicate
    findings on the same idempotency key. We instead mark stale scans as failed
    in a follow-up PR. For Phase B we only log the count.
    """
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(func.count(Scan.id)).where(Scan.aggregate_score == 0))
        stale_count = int(result.scalar_one())
        if stale_count > 0:
            logger.info("startup: %d scan(s) appear to be incomplete", stale_count)
