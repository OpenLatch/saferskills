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
from app.models.scan_run import ScanRun
from app.scan import engine, persistence

logger = logging.getLogger(__name__)


STAGES_SCORING = ("security", "supply_chain", "maintenance", "transparency", "community")


async def _next_event_seq(
    session: AsyncSession, *, scan_run_id: UUID | None = None, scan_id: UUID | None = None
) -> int:
    cond = (
        ScanEvent.scan_run_id == scan_run_id
        if scan_run_id is not None
        else ScanEvent.scan_id == scan_id
    )
    max_seq = (
        await session.execute(select(func.coalesce(func.max(ScanEvent.event_seq), 0)).where(cond))
    ).scalar_one()
    return int(max_seq) + 1


async def _emit(
    channel_id: UUID,
    stage: str,
    completion_pct: int,
    status: str,
    payload: dict[str, Any] | None = None,
    *,
    scan_run_id: UUID | None = None,
    scan_id: UUID | None = None,
) -> None:
    """Append a scan_events row + NOTIFY listening SSE consumers on
    `scan_progress_<channel_id>`. Repo-scan progress keys on `scan_run_id`
    (the SSE channel the frontend subscribes to); the legacy single-scan path
    keys on `scan_id`."""
    async with AsyncSessionLocal() as session:
        event_seq = await _next_event_seq(session, scan_run_id=scan_run_id, scan_id=scan_id)
        event = ScanEvent(
            scan_run_id=scan_run_id,
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
    channel = f"scan_progress_{channel_id.hex}"
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
        await _emit(scan_id, "fetch", 5, "running", {"target": github_url}, scan_id=scan_id)

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
            scan_id=scan_id,
        )

        await _emit(
            scan_id, "index", 25, "completed", {"file_count": result.file_count}, scan_id=scan_id
        )

        for sub_score, target_pct in zip(STAGES_SCORING, (50, 65, 75, 85, 90), strict=True):
            count = sum(1 for f in result.findings if f.sub_score == sub_score)
            await _emit(
                scan_id,
                sub_score,
                target_pct,
                "completed",
                {"findings_count": count, "sub_score": result.sub_scores.get(sub_score, 100)},
                scan_id=scan_id,
            )

        await _emit(
            scan_id,
            "score",
            98,
            "completed",
            {"aggregate_score": result.aggregate_score, "tier": result.tier},
            scan_id=scan_id,
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

        await _emit(scan_id, "sign", 100, "completed", scan_id=scan_id)
        await _emit(scan_id, "done", 100, "completed", scan_id=scan_id)

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
                scan_id=scan_id,
            )
        except Exception:
            # Best-effort — emit may itself fail if the pool is down.
            logger.exception("scan %s final emit also failed", scan_id)


async def scan_run_repo(
    run_id: UUID,
    github_url: str,
    rubric_version: str,
) -> None:
    """Drive one repo scan to completion: discover + score N capabilities, fan
    out to N catalog items + N scans under the run, emit progress on
    `scan_progress_<run_id>`. Modeled on `scan_run`; always terminal.
    """
    try:
        await _emit(run_id, "fetch", 5, "running", {"target": github_url}, scan_run_id=run_id)

        repo = await engine.run_repo_scan(github_url, rubric_version)

        await _emit(
            run_id,
            "fetch",
            15,
            "completed",
            {"file_count": repo.file_count, "ref_sha": repo.ref_sha},
            scan_run_id=run_id,
        )
        await _emit(
            run_id,
            "index",
            25,
            "completed",
            {"file_count": repo.file_count, "capability_count": repo.capability_count},
            scan_run_id=run_id,
        )

        for sub_score, target_pct in zip(STAGES_SCORING, (50, 65, 75, 85, 90), strict=True):
            count = sum(
                1
                for cap in repo.capabilities
                for f in cap.result.findings
                if f.sub_score == sub_score
            )
            await _emit(
                run_id,
                sub_score,
                target_pct,
                "completed",
                {"findings_count": count},
                scan_run_id=run_id,
            )

        await _emit(
            run_id,
            "score",
            98,
            "completed",
            {
                "repo_aggregate_score": repo.repo_aggregate_score,
                "repo_tier": repo.repo_tier,
                "kind_tally": repo.kind_tally,
            },
            scan_run_id=run_id,
        )

        async with AsyncSessionLocal() as session:
            run = (
                await session.execute(select(ScanRun).where(ScanRun.id == run_id))
            ).scalar_one_or_none()
            if run is None:
                logger.warning("scan_run %s vanished mid-run; skipping commit", run_id)
            else:
                await persistence.persist_completed_scan_run(session, run, repo)
                await session.commit()

        await _emit(run_id, "sign", 100, "completed", scan_run_id=run_id)
        await _emit(run_id, "done", 100, "completed", scan_run_id=run_id)

    except Exception as exc:
        logger.exception("scan_run %s failed", run_id)
        # Best-effort: flip the run to failed so the report surface shows it.
        try:
            async with AsyncSessionLocal() as session:
                run = (
                    await session.execute(select(ScanRun).where(ScanRun.id == run_id))
                ).scalar_one_or_none()
                if run is not None:
                    run.status = "failed"
                    await session.commit()
        except Exception:
            logger.exception("scan_run %s failed-status update also failed", run_id)
        try:
            await _emit(
                run_id,
                "done",
                100,
                "failed",
                {
                    "error_class": type(exc).__name__,
                    "error_message": str(exc),
                    "traceback_tail": traceback.format_exc(limit=3),
                },
                scan_run_id=run_id,
            )
        except Exception:
            logger.exception("scan_run %s final emit also failed", run_id)


async def scan_run_upload(
    run_id: UUID,
    files_index: list[tuple[str, bytes]],
    rubric_version: str,
) -> None:
    """Drive one UPLOAD repo scan to completion (I-3.5).

    Identical to `scan_run_repo` except the engine scores the pre-extracted
    in-memory file index instead of fetching from GitHub (re-fetching is
    impossible for uploads). Streams the same `scan_progress_<run_id>` events and
    persists via the same fork in `persist_completed_scan_run`; `files_index` is
    threaded through so unlisted uploads can store their bytes per-run.
    """
    try:
        await _emit(run_id, "fetch", 5, "running", {"target": "upload"}, scan_run_id=run_id)

        repo = engine.run_repo_scan_from_index(files_index, rubric_version, source_kind="upload")

        await _emit(
            run_id,
            "fetch",
            15,
            "completed",
            {"file_count": repo.file_count, "ref_sha": repo.ref_sha},
            scan_run_id=run_id,
        )
        await _emit(
            run_id,
            "index",
            25,
            "completed",
            {"file_count": repo.file_count, "capability_count": repo.capability_count},
            scan_run_id=run_id,
        )

        for sub_score, target_pct in zip(STAGES_SCORING, (50, 65, 75, 85, 90), strict=True):
            count = sum(
                1
                for cap in repo.capabilities
                for f in cap.result.findings
                if f.sub_score == sub_score
            )
            await _emit(
                run_id,
                sub_score,
                target_pct,
                "completed",
                {"findings_count": count},
                scan_run_id=run_id,
            )

        await _emit(
            run_id,
            "score",
            98,
            "completed",
            {
                "repo_aggregate_score": repo.repo_aggregate_score,
                "repo_tier": repo.repo_tier,
                "kind_tally": repo.kind_tally,
            },
            scan_run_id=run_id,
        )

        async with AsyncSessionLocal() as session:
            run = (
                await session.execute(select(ScanRun).where(ScanRun.id == run_id))
            ).scalar_one_or_none()
            if run is None:
                logger.warning("scan_run %s vanished mid-run; skipping commit", run_id)
            else:
                await persistence.persist_completed_scan_run(
                    session, run, repo, full_files_index=files_index
                )
                await session.commit()

        await _emit(run_id, "sign", 100, "completed", scan_run_id=run_id)
        await _emit(run_id, "done", 100, "completed", scan_run_id=run_id)

    except Exception as exc:
        logger.exception("scan_run_upload %s failed", run_id)
        try:
            async with AsyncSessionLocal() as session:
                run = (
                    await session.execute(select(ScanRun).where(ScanRun.id == run_id))
                ).scalar_one_or_none()
                if run is not None:
                    run.status = "failed"
                    await session.commit()
        except Exception:
            logger.exception("scan_run_upload %s failed-status update also failed", run_id)
        try:
            await _emit(
                run_id,
                "done",
                100,
                "failed",
                {
                    "error_class": type(exc).__name__,
                    "error_message": str(exc),
                    "traceback_tail": traceback.format_exc(limit=3),
                },
                scan_run_id=run_id,
            )
        except Exception:
            logger.exception("scan_run_upload %s final emit also failed", run_id)


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
