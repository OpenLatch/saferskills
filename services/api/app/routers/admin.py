"""Admin endpoints (D-04-28) — gated by the `X-Admin-Key` header.

Every mutation writes one `admin_audit_log` row (security.md Audit-trail
invariant). The gate fails CLOSED: when `SAFERSKILLS_ADMIN_KEY` is unset, every
endpoint returns 403 — EXCEPT under local development (`ENV=development`), which is
exempt and audits as `local-dev`. Real deploys always set `ENV=staging`/`production`
so the exemption can never apply off a developer's machine. Driven by the
`saferskills-admin` CLI. When auth lands (Track E) the X-Admin-Key gate is replaced
by SSO; the CLI keeps working.

Endpoints (mounted at /api/v1/admin):
  GET  /sources                          eagle-eye snapshot: summary rollup +
                                         critical[] + rich per-provider detail
  GET  /sources/{source}/runs            keyset-paginated ingestion_runs history
  POST /sources/{source}/pause           pause (reason, contact)
  POST /sources/{source}/unpause         re-activate
  POST /sources/{source}/force-cycle     defer one adapter cycle (trigger='force')
  GET  /merge-candidates                  list (status, limit)
  POST /merge-candidates/{id}/decide      merged | rejected
  POST /catalog/{slug}/re-classify        re-run kind/quality/agent heuristics
  GET  /catalog/{slug}/events             inspect ingestion_events
  POST /catalog/{slug}/archive            force archive
  POST /catalog/{slug}/un-archive         restore
  POST /popularity/recompute-now          defer popularity_recompute
  GET  /popularity/top-n                  top-N by popularity_score
"""

from __future__ import annotations

import datetime as dt
import hashlib
import secrets
import time
from typing import Any, cast
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Query
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent_scan.persistence import delete_agent_run_cascade
from app.core.config import get_settings
from app.db.session import get_session
from app.ingestion.config.loader import load_source_configs
from app.ingestion.framework import health
from app.ingestion.framework.classifier import CLASSIFIER_VERSION, classify_all
from app.ingestion.framework.halt import get_source_status, set_source_status
from app.models import AdminAuditLog, CatalogItem
from app.models.generated.agent_run import AgentRun
from app.models.generated.merge_candidate import MergeCandidate

router = APIRouter(prefix="/admin", tags=["admin"])


# ─── Auth ────────────────────────────────────────────────────────────────────


async def require_admin_key(
    x_admin_key: str | None = Header(default=None, alias="X-Admin-Key"),
) -> str:
    """Validate the X-Admin-Key header; return a short fingerprint for the audit log.

    A configured SAFERSKILLS_ADMIN_KEY is mandatory (constant-time compare). When the
    key is unset, local development (ENV=development) is exempt and audits as
    "local-dev"; every other environment fails closed (403)."""
    settings = get_settings()
    expected = settings.saferskills_admin_key
    if expected:
        if x_admin_key and secrets.compare_digest(x_admin_key, expected):
            return hashlib.sha256(x_admin_key.encode()).hexdigest()[:20]
        raise HTTPException(status_code=403, detail="invalid admin key")
    if settings.env == "development":
        return "local-dev"
    raise HTTPException(status_code=403, detail="invalid admin key")


def _json_safe(value: Any) -> Any:
    """Recursively ISO-format datetimes so a before/after snapshot is JSONB-safe."""
    if isinstance(value, dt.datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in cast("dict[str, Any]", value).items()}
    if isinstance(value, list):
        return [_json_safe(v) for v in cast("list[Any]", value)]
    return value


async def _audit(
    session: AsyncSession,
    *,
    action: str,
    actor_fp: str,
    target: str | None,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    note: str = "",
) -> None:
    """Add the audit row and commit — this is the SINGLE commit per mutation, so
    the domain change (still pending in the session) and its audit row land
    atomically. Callers must NOT commit before calling this."""
    session.add(
        AdminAuditLog(
            action=action,
            actor_admin_key_fp=actor_fp,
            target=target,
            before=_json_safe(before) if before is not None else None,
            after=_json_safe(after) if after is not None else None,
            note=note or None,
        )
    )
    await session.commit()


# ─── Sources ─────────────────────────────────────────────────────────────────


def _iso(value: dt.datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


_LAST_RUN_SQL = text("""
    SELECT DISTINCT ON (source)
        source, id, trigger, status, started_at, ended_at, duration_ms,
        items_seen, items_added, items_updated, http_304_count, http_5xx_count,
        attempt, error_class, error_message
    FROM ingestion_runs
    ORDER BY source, started_at DESC
""")

# Rolling 1h/24h windows + the oldest still-running row per source. Bounded to
# 24h OR running, so the (source, started_at DESC) + partial running indexes apply.
_RUN_AGG_SQL = text("""
    SELECT source,
        count(*) FILTER (WHERE started_at > now() - interval '1 hour')                          AS total_1h,
        count(*) FILTER (WHERE status='failed' AND started_at > now() - interval '1 hour')      AS failed_1h,
        count(*) FILTER (WHERE started_at > now() - interval '24 hours')                        AS total_24h,
        count(*) FILTER (WHERE status='failed' AND started_at > now() - interval '24 hours')    AS failed_24h,
        min(started_at) FILTER (WHERE status='running')                                         AS running_since
    FROM ingestion_runs
    WHERE started_at > now() - interval '24 hours' OR status = 'running'
    GROUP BY source
""")

_PROC_SQL = text("""
    SELECT task_name,
        count(*) FILTER (WHERE status='doing')  AS doing,
        count(*) FILTER (WHERE status='failed') AS failed,
        min(scheduled_at) FILTER (WHERE status='todo' AND scheduled_at IS NOT NULL) AS next_scheduled
    FROM procrastinate_jobs
    WHERE task_name LIKE 'ingest_cycle_%'
    GROUP BY task_name
""")


@router.get("/sources")
async def admin_list_sources(
    _: str = Depends(require_admin_key),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Eagle-eye pipeline snapshot: every YAML source merged with its
    crawler_cursors status, last ingestion_runs row + rolling failure windows,
    live/dead-letter/next-retry from procrastinate_jobs, croniter schedule, and a
    derived health verdict — plus a top-level summary rollup + deduped critical[].

    Additive over the original endpoint: every prior field name is preserved; the
    `live` / `last_run` / `schedule` / `health` objects are new nested additions.
    """
    configs = load_source_configs()
    now = dt.datetime.now(tz=dt.UTC)

    cursors = {
        r.source: r
        for r in (
            await session.execute(
                text("""
            SELECT source, status, status_reason, status_contact, status_changed_at,
                   last_successful_cycle_at, last_attempted_cycle_at, consecutive_failure_count
            FROM crawler_cursors
        """)
            )
        ).all()
    }
    last_runs = {r.source: r for r in (await session.execute(_LAST_RUN_SQL)).all()}
    aggs = {r.source: r for r in (await session.execute(_RUN_AGG_SQL)).all()}

    # procrastinate_jobs is applied at boot (not by Alembic), so it may be absent
    # in a fresh DB / under the test ASGITransport — guard before querying.
    proc: dict[str, Any] = {}
    if (
        await session.execute(text("SELECT to_regclass('procrastinate_jobs')"))
    ).scalar() is not None:
        proc = {
            r.task_name.removeprefix("ingest_cycle_"): r
            for r in (await session.execute(_PROC_SQL)).all()
        }

    data: list[dict[str, Any]] = []
    signals: list[health.CriticalSignal] = []
    by_status: dict[str, int] = {}

    for name, cfg in sorted(configs.items()):
        cur = cursors.get(name)
        agg = aggs.get(name)
        lr = last_runs.get(name)
        pj = proc.get(name)

        cursor_status = cur.status if cur else "active"
        last_success = cur.last_successful_cycle_at if cur else None
        last_attempt = cur.last_attempted_cycle_at if cur else None
        consecutive_failures = cur.consecutive_failure_count if cur else 0
        running_since = agg.running_since if agg else None
        has_live = bool(pj and pj.doing)
        has_dead_letter = bool(pj and pj.failed)

        snap = health.SourceSnapshot(
            source=name,
            enabled=cfg.enabled,
            cursor_status=cursor_status,
            consecutive_failures=consecutive_failures,
            last_success_at=last_success,
            last_attempt_at=last_attempt,
            cadence_cron=cfg.cadence_cron,
            has_live_job=has_live,
            has_dead_letter=has_dead_letter,
            running_since=running_since,
            runs_total_1h=agg.total_1h if agg else 0,
            runs_failed_1h=agg.failed_1h if agg else 0,
            runs_total_24h=agg.total_24h if agg else 0,
            runs_failed_24h=agg.failed_24h if agg else 0,
            now=now,
        )
        derived = health.derive_status(snap)
        by_status[derived] = by_status.get(derived, 0) + 1
        signal = health.classify_critical(snap)
        if signal is not None:
            signals.append(signal)

        next_expected = health.next_expected_run(cfg.cadence_cron, now)
        data.append(
            {
                # ── original fields (unchanged) ──
                "source": name,
                "kind": cfg.kind,
                "cadence": cfg.cadence_cron,
                "enabled": cfg.enabled,
                "registry_id": cfg.registry_id,
                "policy_summary": cfg.policy.summary,
                "status": cursor_status,
                "status_reason": cur.status_reason if cur else None,
                "last_successful_cycle_at": _iso(last_success),
                "consecutive_failure_count": consecutive_failures,
                # ── new nested detail ──
                "live": {
                    "running": has_live or running_since is not None,
                    "running_since": _iso(running_since),
                    "dead_letter": has_dead_letter,
                },
                "last_run": (
                    {
                        "id": str(lr.id),
                        "trigger": lr.trigger,
                        "status": lr.status,
                        "started_at": _iso(lr.started_at),
                        "ended_at": _iso(lr.ended_at),
                        "duration_ms": lr.duration_ms,
                        "items_seen": lr.items_seen,
                        "items_added": lr.items_added,
                        "items_updated": lr.items_updated,
                        "http_304_count": lr.http_304_count,
                        "http_5xx_count": lr.http_5xx_count,
                        "error_class": lr.error_class,
                        "error_message": lr.error_message,
                    }
                    if lr is not None
                    else None
                ),
                "schedule": {
                    "cadence_cron": cfg.cadence_cron,
                    "next_expected_run": _iso(next_expected),
                    "next_retry_at": _iso(pj.next_scheduled) if pj else None,
                    "overdue": health.is_overdue(snap),
                },
                "health": {
                    "status": derived,
                    "reason_code": signal.reason_code if signal else None,
                    "tier": signal.tier if signal else None,
                    "failure_rate_1h": round(health.failure_rate_1h(snap), 4),
                    "failure_rate_24h": round(health.failure_rate_24h(snap), 4),
                    "runs_24h": snap.runs_total_24h,
                    "consecutive_failures": consecutive_failures,
                    "last_success_at": _iso(last_success),
                    "last_attempt_at": _iso(last_attempt),
                },
            }
        )

    critical = sorted(
        (
            {"source": s.source, "reason_code": s.reason_code, "tier": s.tier, "detail": s.detail}
            for s in signals
        ),
        key=lambda c: (c["tier"] != "critical", c["source"]),
    )
    return {
        "generated_at": now.isoformat(),
        "summary": {
            "overall": health.rollup_overall(signals),
            "total": len(data),
            "by_status": by_status,
            "critical_count": sum(1 for s in signals if s.tier == "critical"),
            "warn_count": sum(1 for s in signals if s.tier == "warn"),
        },
        "critical": critical,
        "data": data,
    }


@router.get("/sources/{source}/runs")
async def admin_source_runs(
    source: str,
    limit: int = Query(default=50, ge=1, le=200),
    before: dt.datetime | None = Query(
        default=None, description="Keyset cursor — return runs with started_at < this."
    ),
    _: str = Depends(require_admin_key),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Keyset-paginated `ingestion_runs` history for one source (started_at DESC)."""
    if source not in load_source_configs():
        raise HTTPException(404, f"unknown source {source!r}")
    sql = """
        SELECT id, source, trigger, status, started_at, ended_at, duration_ms,
               items_seen, items_added, items_updated, http_304_count, http_5xx_count,
               attempt, error_class, error_message
        FROM ingestion_runs
        WHERE source = :source
    """
    params: dict[str, Any] = {"source": source, "limit": limit}
    if before is not None:
        sql += " AND started_at < :before"
        params["before"] = before
    sql += " ORDER BY started_at DESC LIMIT :limit"
    rows = (await session.execute(text(sql), params)).all()
    data = [
        {
            "id": str(r.id),
            "source": r.source,
            "trigger": r.trigger,
            "status": r.status,
            "started_at": _iso(r.started_at),
            "ended_at": _iso(r.ended_at),
            "duration_ms": r.duration_ms,
            "items_seen": r.items_seen,
            "items_added": r.items_added,
            "items_updated": r.items_updated,
            "http_304_count": r.http_304_count,
            "http_5xx_count": r.http_5xx_count,
            "attempt": r.attempt,
            "error_class": r.error_class,
            "error_message": r.error_message,
        }
        for r in rows
    ]
    next_before = data[-1]["started_at"] if len(data) == limit else None
    return {"data": data, "next_before": next_before}


@router.post("/sources/{source}/pause")
async def admin_pause_source(
    source: str,
    payload: dict[str, Any] = Body(default_factory=dict),
    actor_fp: str = Depends(require_admin_key),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    before = await get_source_status(session, source)
    if before is None:
        raise HTTPException(404, f"unknown source {source!r}")
    after = await set_source_status(
        session,
        source,
        status="paused",
        reason=payload.get("reason"),
        contact=payload.get("contact"),
    )
    await _audit(
        session,
        action="sources.pause",
        actor_fp=actor_fp,
        target=source,
        before=before,
        after=after,
        note=payload.get("reason", ""),
    )
    return {"ok": True, "status": after}


@router.post("/sources/{source}/unpause")
async def admin_unpause_source(
    source: str,
    actor_fp: str = Depends(require_admin_key),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    before = await get_source_status(session, source)
    if before is None:
        raise HTTPException(404, f"unknown source {source!r}")
    after = await set_source_status(session, source, status="active")
    await _audit(
        session,
        action="sources.unpause",
        actor_fp=actor_fp,
        target=source,
        before=before,
        after=after,
    )
    return {"ok": True, "status": after}


@router.post("/sources/{source}/force-cycle")
async def admin_force_cycle_source(
    source: str,
    actor_fp: str = Depends(require_admin_key),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    if source not in load_source_configs():
        raise HTTPException(404, f"unknown source {source!r}")
    from procrastinate.exceptions import AlreadyEnqueued, TaskNotFound

    from app.ingestion import procrastinate_app

    # Pre-check the per-source `queueing_lock` (the same lock-aware pattern as
    # `tasks_scan.defer_scan_job`): a cycle already `todo`/`doing` holds
    # `ingest_cycle_<source>_lock`, so a second defer would raise AlreadyEnqueued.
    # Surface that as an honest 409 — the source IS schedulable, it's just busy —
    # instead of the old broad-except "not schedulable" mislabel (the dashboard's
    # misleading "3 failed" after a force-cycle ALL). Best-effort: a list_jobs
    # error falls through to the defer, where AlreadyEnqueued is the race backstop.
    lock = f"ingest_cycle_{source}_lock"
    try:
        existing: list[Any] = list(
            await procrastinate_app.job_manager.list_jobs_async(queueing_lock=lock)
        )
    except Exception:
        existing = []
    if any(getattr(j, "status", None) in ("todo", "doing") for j in existing):
        raise HTTPException(409, f"a cycle is already queued or running for {source!r}")

    try:
        # allow_unknown=False so a non-cadenced source (webhook/disabled — no
        # registered `ingest_cycle_*` task) raises TaskNotFound instead of
        # silently queueing an orphan job no worker ever runs.
        await procrastinate_app.configure_task(
            name=f"ingest_cycle_{source}", allow_unknown=False
        ).defer_async(timestamp=int(time.time()), trigger="force")
    except AlreadyEnqueued as exc:
        # Race backstop: a concurrent defer claimed the lock between the pre-check
        # and here. Same honest 409 as the pre-check.
        raise HTTPException(409, f"a cycle is already queued or running for {source!r}") from exc
    except TaskNotFound as exc:
        # No registered periodic `ingest_cycle_*` task — a webhook or disabled
        # source. Keep 400 (correct to reject) but reword: the old message claimed
        # "not schedulable (disabled or non-api)" even for a genuine webhook.
        raise HTTPException(
            400, f"{source!r} has no periodic cycle (webhook or disabled source)"
        ) from exc
    # Any other exception propagates → 500: a real bug must not be swallowed as a
    # benign "not schedulable".
    await _audit(session, action="sources.force_cycle", actor_fp=actor_fp, target=source)
    return {"ok": True, "queued": True}


# ─── Merge candidates ────────────────────────────────────────────────────────


@router.get("/merge-candidates")
async def admin_list_merge_candidates(
    status: str = Query(default="pending"),
    limit: int = Query(default=20, ge=1, le=200),
    _: str = Depends(require_admin_key),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    rows = (
        (
            await session.execute(
                select(MergeCandidate)
                .where(MergeCandidate.status == status)
                .order_by(MergeCandidate.created_at.desc())
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    return {
        "data": [
            {
                "id": str(mc.id),
                "left_artifact_id": str(mc.left_artifact_id),
                "right_artifact_id": str(mc.right_artifact_id),
                "rapidfuzz_score": mc.rapidfuzz_score,
                "jaro_winkler_score": mc.jaro_winkler_score,
                "status": mc.status,
                "created_at": mc.created_at.isoformat() if mc.created_at else None,
            }
            for mc in rows
        ]
    }


@router.post("/merge-candidates/{candidate_id}/decide")
async def admin_decide_merge_candidate(
    candidate_id: str,
    payload: dict[str, Any] = Body(...),
    actor_fp: str = Depends(require_admin_key),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    decision = payload.get("decision")
    if decision not in {"merged", "rejected"}:
        raise HTTPException(422, "decision must be 'merged' or 'rejected'")
    mc = (
        await session.execute(select(MergeCandidate).where(MergeCandidate.id == candidate_id))
    ).scalar_one_or_none()
    if mc is None:
        raise HTTPException(404, "merge candidate not found")
    before = {"status": mc.status}
    mc.status = decision
    mc.decided_by = actor_fp
    mc.decided_at = dt.datetime.now(tz=dt.UTC)
    mc.decision_note = payload.get("note")
    await _audit(
        session,
        action=f"merge_candidates.{decision}",
        actor_fp=actor_fp,
        target=str(candidate_id),
        before=before,
        after={"status": decision},
        note=payload.get("note", ""),
    )
    return {"ok": True, "status": decision}


# ─── Catalog ─────────────────────────────────────────────────────────────────


async def _get_item_or_404(session: AsyncSession, slug: str) -> CatalogItem:
    item = (
        await session.execute(select(CatalogItem).where(CatalogItem.slug == slug))
    ).scalar_one_or_none()
    if item is None:
        raise HTTPException(404, f"unknown catalog item {slug!r}")
    return item


def _reconstruct_metadata_files(kind_signals: dict[str, Any]) -> dict[str, bytes]:
    """Best-effort metadata_files from stored kind_signals so re-classify is
    NON-destructive without a network re-fetch (the original file bytes aren't
    stored). Preserves the file-derived kind/agent signals on re-run."""
    files: dict[str, bytes] = {}
    if kind_signals.get("has_skill_md"):
        files["SKILL.md"] = b""
    if kind_signals.get("has_mcp_json"):
        files["mcp.json"] = b"{}"
    if kind_signals.get("has_cursorrules"):
        files[".cursorrules"] = b""
    if kind_signals.get("has_claude_hooks"):
        files[".claude/hooks/hook.json"] = b""
    return files


@router.post("/catalog/{slug}/re-classify")
async def admin_re_classify(
    slug: str,
    actor_fp: str = Depends(require_admin_key),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Re-run the deterministic classifier (D-04-31). Operates on stored signals
    (no network re-fetch): metadata_files are reconstructed from the stored
    kind_signals so file-derived kind/agent classifications are preserved while
    quality_tier recomputes from current stars/downloads."""
    from app.ingestion.framework.base_adapter import NormalizedItem

    item = await _get_item_or_404(session, slug)
    meta = dict(item.item_metadata or {})
    n = NormalizedItem(
        github_org=item.github_org,
        github_repo=item.github_repo,
        display_name=item.display_name,
        description=str(meta.get("description") or ""),
        license_spdx=item.license_spdx,
        github_url=item.github_url,
        kind=item.kind,
        stars=item.github_stars,
        weekly_downloads=meta.get("weekly_downloads"),
        pushed_at=meta.get("pushed_at"),
        metadata_files=_reconstruct_metadata_files(dict(item.kind_signals or {})),
    )
    kind, kind_signals, quality_tier, quality_signals, agents = classify_all(n)
    before = {
        "kind": item.kind,
        "quality_tier": item.quality_tier,
        "agent_compatibility": list(item.agent_compatibility or []),
    }
    item.kind = kind
    item.kind_signals = kind_signals
    item.quality_tier = quality_tier
    item.quality_signals = quality_signals
    item.agent_compatibility = agents
    item.updated_at = dt.datetime.now(tz=dt.UTC)
    after = {"kind": kind, "quality_tier": quality_tier, "agent_compatibility": agents}
    await _audit(
        session,
        action="catalog.re_classify",
        actor_fp=actor_fp,
        target=slug,
        before=before,
        after=after,
        note=f"classifier={CLASSIFIER_VERSION}",
    )
    return {"ok": True, "before": before, "after": after}


@router.get("/catalog/{slug}/events")
async def admin_inspect_events(
    slug: str,
    limit: int = Query(default=50, ge=1, le=200),
    _: str = Depends(require_admin_key),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Recent ingestion_events whose payload references this slug (best-effort —
    the outbox keys on source_id, so this matches payload->>'slug')."""
    await _get_item_or_404(session, slug)
    rows = (
        await session.execute(
            text("""
            SELECT id, source, source_id, http_status, fetched_at, from_cache, fetch_tier, applied_at
            FROM ingestion_events
            WHERE payload->>'slug' = :slug
            ORDER BY fetched_at DESC
            LIMIT :limit
        """),
            {"slug": slug, "limit": limit},
        )
    ).all()
    return {
        "data": [
            {
                "id": str(r.id),
                "source": r.source,
                "source_id": r.source_id,
                "http_status": r.http_status,
                "fetched_at": r.fetched_at.isoformat() if r.fetched_at else None,
                "from_cache": r.from_cache,
                "fetch_tier": r.fetch_tier,
                "applied_at": r.applied_at.isoformat() if r.applied_at else None,
            }
            for r in rows
        ]
    }


@router.post("/catalog/{slug}/archive")
async def admin_archive_item(
    slug: str,
    payload: dict[str, Any] = Body(default_factory=dict),
    actor_fp: str = Depends(require_admin_key),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    item = await _get_item_or_404(session, slug)
    before = {"archived": item.archived, "availability": item.availability}
    item.archived = True
    item.availability = "archived"
    item.updated_at = dt.datetime.now(tz=dt.UTC)
    await _audit(
        session,
        action="catalog.archive",
        actor_fp=actor_fp,
        target=slug,
        before=before,
        after={"archived": True, "availability": "archived"},
        note=payload.get("reason", ""),
    )
    return {"ok": True}


@router.post("/catalog/{slug}/un-archive")
async def admin_un_archive_item(
    slug: str,
    actor_fp: str = Depends(require_admin_key),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    item = await _get_item_or_404(session, slug)
    before = {"archived": item.archived, "availability": item.availability}
    item.archived = False
    item.availability = "available"
    item.updated_at = dt.datetime.now(tz=dt.UTC)
    await _audit(
        session,
        action="catalog.un_archive",
        actor_fp=actor_fp,
        target=slug,
        before=before,
        after={"archived": False, "availability": "available"},
    )
    return {"ok": True}


# ─── Popularity ──────────────────────────────────────────────────────────────


@router.post("/popularity/recompute-now")
async def admin_recompute_popularity_now(
    actor_fp: str = Depends(require_admin_key),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    from app.ingestion import procrastinate_app

    # Defer by name (matches force-cycle) — configure_task's deferrer accepts the
    # task's kwargs; the periodic task takes `timestamp`.
    await procrastinate_app.configure_task(name="popularity_recompute").defer_async(
        timestamp=int(time.time())
    )
    await _audit(session, action="popularity.recompute_now", actor_fp=actor_fp, target=None)
    return {"ok": True, "queued": True}


@router.get("/popularity/top-n")
async def admin_popularity_top_n(
    n: int = Query(default=500, ge=1, le=5000),
    kind: str | None = Query(default=None),
    _: str = Depends(require_admin_key),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    sql = """
        SELECT slug, kind, popularity_score, popularity_rank_tier,
               last_scanned_at, scanned_rubric_version
        FROM catalog_items
        WHERE archived = false AND source_kind = 'github' AND visibility = 'public'
    """
    params: dict[str, Any] = {"limit": n}
    if kind is not None:
        sql += " AND kind = :kind"
        params["kind"] = kind
    sql += " ORDER BY popularity_score DESC NULLS LAST, slug LIMIT :limit"
    rows = (await session.execute(text(sql), params)).all()
    return {
        "data": [
            {
                "slug": r.slug,
                "kind": r.kind,
                "popularity_score": r.popularity_score,
                "popularity_rank_tier": r.popularity_rank_tier,
                "last_scanned_at": (r.last_scanned_at.isoformat() if r.last_scanned_at else None),
                "scanned_rubric_version": r.scanned_rubric_version,
            }
            for r in rows
        ]
    }


# ─── Agent scan (I-5.5) ───────────────────────────────────────────────────────


@router.delete("/agent-scans/{run_id}")
async def admin_delete_agent_run(
    run_id: UUID,
    actor_fp: str = Depends(require_admin_key),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Admin-only delete of an Agent Report (public reports are user-irreversible;
    D-5.5-20). Cascades findings/telemetry/evidence, writes one audit row. 404 if
    absent. Never touches `artifact_blobs`; the token ledger is reaped by sweep."""
    run = await session.get(AgentRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="not found")
    before = {
        "id": str(run.id),
        "visibility": run.visibility,
        "status": run.status,
        "band": run.band,
        "score": run.score,
    }
    await delete_agent_run_cascade(session, run_id, allow_public=True)
    await _audit(
        session,
        action="agent_scan_delete",
        actor_fp=actor_fp,
        target=str(run_id),
        before=before,
        after=None,
        note="admin delete",
    )
    return {"deleted": True}
