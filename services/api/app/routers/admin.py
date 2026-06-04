"""Admin endpoints (D-04-28) — gated by the `X-Admin-Key` header.

Every mutation writes one `admin_audit_log` row (security.md Audit-trail
invariant). The gate fails CLOSED: when `SAFERSKILLS_ADMIN_KEY` is unset, every
endpoint returns 403 — EXCEPT under local development (`ENV=development`), which is
exempt and audits as `local-dev`. Real deploys always set `ENV=staging`/`production`
so the exemption can never apply off a developer's machine. Driven by the
`saferskills-admin` CLI. When auth lands (Track E) the X-Admin-Key gate is replaced
by SSO; the CLI keeps working.

Endpoints (mounted at /api/v1/admin):
  GET  /sources                          list 14 sources + status
  POST /sources/{source}/pause           pause (reason, contact)
  POST /sources/{source}/unpause         re-activate
  POST /sources/{source}/force-cycle     defer one adapter cycle
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

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Query
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.session import get_session
from app.ingestion.config.loader import load_source_configs
from app.ingestion.framework.classifier import CLASSIFIER_VERSION, classify_all
from app.ingestion.framework.halt import get_source_status, set_source_status
from app.models import AdminAuditLog, CatalogItem
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


@router.get("/sources")
async def admin_list_sources(
    _: str = Depends(require_admin_key),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """All YAML-declared sources merged with their crawler_cursors status."""
    configs = load_source_configs()
    rows = {
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
    data: list[dict[str, Any]] = []
    for name, cfg in sorted(configs.items()):
        cur = rows.get(name)
        data.append(
            {
                "source": name,
                "kind": cfg.kind,
                "cadence": cfg.cadence_cron,
                "enabled": cfg.enabled,
                "registry_id": cfg.registry_id,
                "policy_summary": cfg.policy.summary,
                "status": cur.status if cur else "active",
                "status_reason": cur.status_reason if cur else None,
                "last_successful_cycle_at": (
                    cur.last_successful_cycle_at.isoformat()
                    if cur and cur.last_successful_cycle_at
                    else None
                ),
                "consecutive_failure_count": cur.consecutive_failure_count if cur else 0,
            }
        )
    return {"data": data}


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
    from app.ingestion import procrastinate_app

    try:
        await procrastinate_app.configure_task(name=f"ingest_cycle_{source}").defer_async(
            timestamp=int(time.time())
        )
    except Exception as exc:  # task not registered (disabled/non-api source)
        raise HTTPException(
            400, f"source {source!r} is not schedulable (disabled or non-api)"
        ) from exc
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
               last_deep_scan_at, last_lite_scan_at
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
                "last_deep_scan_at": (
                    r.last_deep_scan_at.isoformat() if r.last_deep_scan_at else None
                ),
                "last_lite_scan_at": (
                    r.last_lite_scan_at.isoformat() if r.last_lite_scan_at else None
                ),
            }
            for r in rows
        ]
    }
