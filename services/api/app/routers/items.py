"""Catalog browse surface — list + detail + facets.

Reads `catalog_items` + optionally joins on the most-recent `scans` row to
project `latest_scan_score` / `latest_scan_tier` per item. Phase B supports
keyset-style cursor pagination + a small set of filters that the catalog
filter sidebar drives.
"""

from __future__ import annotations

import base64
import logging
from collections.abc import Sequence
from datetime import datetime, timedelta
from typing import Literal, cast

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.models.catalog_item import CatalogItem
from app.models.item_source import ItemSource
from app.models.scan import Finding, Scan
from app.models.vendor import VendorResponse
from app.queries import latest_scan_tier_distribution
from app.scan.report_builder import build_scan_report_detail
from app.schemas.catalog_summary import (
    CatalogFacets,
    CatalogItemDetail,
    CatalogItemSummary,
    CatalogListEnvelope,
)
from app.schemas.item_detail import (
    AgentShare,
    InstallActivity,
    ItemDetailResponse,
    ManifestSource,
    RelatedItem,
    RepoMeta,
    ScanHistoryPoint,
    VendorResponsePublic,
    VersionPoint,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/items", tags=["items"])


SortKey = Literal["most_installed", "recent", "highest_score", "lowest_score", "most_starred"]


def _encode_cursor(value: str) -> str:
    return base64.urlsafe_b64encode(value.encode("utf-8")).decode("ascii").rstrip("=")


def _decode_cursor(cursor: str) -> str:
    padding = "=" * (-len(cursor) % 4)
    try:
        return base64.urlsafe_b64decode(cursor + padding).decode("utf-8")
    except (ValueError, UnicodeDecodeError) as exc:
        raise HTTPException(status_code=400, detail="invalid cursor") from exc


def _to_summary(
    item: CatalogItem,
    *,
    latest_score: int | None,
    latest_tier: str | None,
    latest_scan_at: datetime | None,
    findings_count: int,
    registries: Sequence[str],
) -> CatalogItemSummary:
    return CatalogItemSummary(
        id=str(item.id),
        slug=item.slug,
        kind=item.kind,  # type: ignore[arg-type]
        display_name=item.display_name,
        description=(
            item.item_metadata.get("description") if isinstance(item.item_metadata, dict) else None
        ),
        github_url=item.github_url,
        github_org=item.github_org,
        github_repo=item.github_repo,
        popularity_tier=item.popularity_tier,
        popularity_score=item.popularity_score,
        latest_scan_score=latest_score,
        latest_scan_tier=latest_tier,  # type: ignore[arg-type]
        latest_scan_at=latest_scan_at,
        findings_count=findings_count,
        registries=list(registries),
        agent_compatibility=list(item.agent_compatibility or []),
        updated_at=item.updated_at,
    )


@router.get("/facets", response_model=CatalogFacets)
async def get_facets(session: AsyncSession = Depends(get_session)) -> CatalogFacets:
    total = (await session.execute(select(func.count(CatalogItem.id)))).scalar_one()

    kind_rows = (
        await session.execute(
            select(CatalogItem.kind, func.count(CatalogItem.id))
            .where(CatalogItem.archived.is_(False))
            .group_by(CatalogItem.kind)
        )
    ).all()
    popularity_rows = (
        await session.execute(
            select(CatalogItem.popularity_tier, func.count(CatalogItem.id))
            .where(CatalogItem.archived.is_(False))
            .group_by(CatalogItem.popularity_tier)
        )
    ).all()
    registry_rows = (
        await session.execute(
            select(ItemSource.registry_id, func.count(ItemSource.id)).group_by(
                ItemSource.registry_id
            )
        )
    ).all()

    # Agent facet: unnest the JSONB agent_compatibility array → per-agent counts.
    # Postgres treats the set-returning function in FROM as a lateral over the
    # preceding catalog_items row, so each item contributes one row per agent.
    agent_fn = func.jsonb_array_elements_text(CatalogItem.agent_compatibility).table_valued("value")
    agent_rows = (
        await session.execute(
            select(agent_fn.c.value, func.count(CatalogItem.id))
            .select_from(CatalogItem, agent_fn)
            .where(CatalogItem.archived.is_(False))
            .group_by(agent_fn.c.value)
        )
    ).all()

    # Tier facet: bucket by latest_scan_tier — shared with /stats (queries.py).
    tier_dist = await latest_scan_tier_distribution(session)

    return CatalogFacets(
        kind={k: int(c) for k, c in kind_rows},
        popularity_tier={k: int(c) for k, c in popularity_rows},
        tier=tier_dist,
        registry={k: int(c) for k, c in registry_rows},
        agent={k: int(c) for k, c in agent_rows},
        total=int(total),
    )


@router.get("", response_model=CatalogListEnvelope)
async def list_items(
    kind: list[str] | None = Query(default=None),
    agent: list[str] | None = Query(default=None),
    popularity_tier: list[str] | None = Query(default=None),
    score_min: int = Query(default=0, ge=0, le=100),
    score_max: int = Query(default=100, ge=0, le=100),
    scan_tier: list[str] | None = Query(default=None),
    q: str | None = Query(default=None, max_length=200),
    sort: SortKey = Query(default="most_installed"),
    limit: int = Query(default=25, ge=1, le=100),
    page: int = Query(default=1, ge=1),
    cursor: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
) -> CatalogListEnvelope:
    """Catalog list with the per-row latest-scan join + filters."""
    latest_scan_sub = select(
        Scan.catalog_item_id.label("ci_id"),
        Scan.aggregate_score.label("latest_score"),
        Scan.tier.label("latest_tier"),
        Scan.scanned_at.label("latest_scanned_at"),
        func.row_number()
        .over(partition_by=Scan.catalog_item_id, order_by=desc(Scan.scanned_at))
        .label("rn"),
    ).subquery()
    latest_scan = (
        select(
            latest_scan_sub.c.ci_id,
            latest_scan_sub.c.latest_score,
            latest_scan_sub.c.latest_tier,
            latest_scan_sub.c.latest_scanned_at,
        )
        .where(latest_scan_sub.c.rn == 1)
        .subquery()
    )

    findings_sub = (
        select(Finding.scan_id, func.count(Finding.id).label("findings_count"))
        .group_by(Finding.scan_id)
        .subquery()
    )

    stmt = (
        select(
            CatalogItem,
            latest_scan.c.latest_score,
            latest_scan.c.latest_tier,
            latest_scan.c.latest_scanned_at,
            func.coalesce(findings_sub.c.findings_count, 0).label("findings_count"),
        )
        .join(latest_scan, latest_scan.c.ci_id == CatalogItem.id, isouter=True)
        .join(
            Scan,
            and_(
                Scan.catalog_item_id == CatalogItem.id,
                Scan.scanned_at == latest_scan.c.latest_scanned_at,
            ),
            isouter=True,
        )
        .join(findings_sub, findings_sub.c.scan_id == Scan.id, isouter=True)
        .where(CatalogItem.archived.is_(False))
    )

    if kind:
        stmt = stmt.where(CatalogItem.kind.in_(kind))
    if popularity_tier:
        stmt = stmt.where(CatalogItem.popularity_tier.in_(popularity_tier))
    if agent:
        # Array-overlap: keep items whose agent_compatibility contains ANY
        # requested agent. JSONB `@>` per agent, OR'd together.
        stmt = stmt.where(or_(*[CatalogItem.agent_compatibility.contains([a]) for a in agent]))
    if scan_tier:
        stmt = stmt.where(latest_scan.c.latest_tier.in_(scan_tier))
    if score_min > 0 or score_max < 100:
        stmt = stmt.where(
            and_(
                func.coalesce(latest_scan.c.latest_score, 0) >= score_min,
                func.coalesce(latest_scan.c.latest_score, 100) <= score_max,
            )
        )
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(CatalogItem.display_name).like(like),
                func.lower(CatalogItem.slug).like(like),
                func.lower(CatalogItem.github_repo).like(like),
            )
        )

    # Filtered total (respects every WHERE applied above) — drives total_pages.
    # Wrap the filtered query in a subquery and count its rows; the latest-scan
    # + findings joins are 1:1 per item so row-count == item-count.
    total = int(
        (
            await session.execute(select(func.count()).select_from(stmt.order_by(None).subquery()))
        ).scalar_one()
    )
    total_pages = max(1, (total + limit - 1) // limit)

    # Legacy keyset cursor (back-compat) takes precedence when supplied;
    # otherwise offset/page pagination drives the numbered pager.
    use_cursor = cursor is not None
    if use_cursor:
        decoded = _decode_cursor(cursor)
        stmt = stmt.where(CatalogItem.slug > decoded)

    if sort == "highest_score":
        stmt = stmt.order_by(desc(func.coalesce(latest_scan.c.latest_score, 0)), CatalogItem.slug)
    elif sort == "lowest_score":
        stmt = stmt.order_by(func.coalesce(latest_scan.c.latest_score, 100), CatalogItem.slug)
    elif sort == "recent":
        stmt = stmt.order_by(desc(CatalogItem.updated_at), CatalogItem.slug)
    elif sort == "most_starred":
        stmt = stmt.order_by(desc(CatalogItem.popularity_score), CatalogItem.slug)
    else:  # most_installed (default)
        stmt = stmt.order_by(desc(CatalogItem.popularity_score), CatalogItem.slug)

    resolved_page = 1 if use_cursor else page
    if not use_cursor:
        stmt = stmt.offset((page - 1) * limit)
    stmt = stmt.limit(limit + 1)
    rows = (await session.execute(stmt)).all()
    has_more = len(rows) > limit
    rows = rows[:limit]

    next_cursor = _encode_cursor(rows[-1][0].slug) if (has_more and rows) else None

    # Per-item registry list — lookup ItemSource.registry_id for each id.
    item_ids = [r[0].id for r in rows]
    registries_by_item: dict[str, list[str]] = {}
    if item_ids:
        reg_rows = (
            await session.execute(
                select(ItemSource.catalog_item_id, ItemSource.registry_id).where(
                    ItemSource.catalog_item_id.in_(item_ids)
                )
            )
        ).all()
        for ci_id, reg_id in reg_rows:
            registries_by_item.setdefault(str(ci_id), []).append(reg_id)

    return CatalogListEnvelope(
        data=[
            _to_summary(
                item,
                latest_score=latest_score,
                latest_tier=latest_tier,
                latest_scan_at=latest_scan_at,
                findings_count=int(findings_count),
                registries=registries_by_item.get(str(item.id), []),
            )
            for item, latest_score, latest_tier, latest_scan_at, findings_count in rows
        ],
        next_cursor=next_cursor,
        total_count=total,
        page=resolved_page,
        total_pages=total_pages,
        page_size=limit,
    )


def _mock_install_activity(popularity_score: int) -> InstallActivity:
    """Deterministic placeholder install counts derived from popularity_score.

    Anonymized counts ONLY — never company-level data (company intelligence is
    OpenLatch's private B2B surface, never public per `.claude/rules/security.md`).
    I-05 (Install CLI) replaces this with real install telemetry.
    """
    all_time = 120 + max(popularity_score, 0) * 7
    this_month = all_time // 4
    this_week = this_month // 4
    return InstallActivity(
        this_week=this_week,
        this_month=this_month,
        all_time=all_time,
        agent_distribution=[
            AgentShare(agent="Claude Code", percentage=62),
            AgentShare(agent="Cursor", percentage=28),
            AgentShare(agent="Others", percentage=10),
        ],
    )


async def _scan_history(
    session: AsyncSession, catalog_item_id: object, *, window_days: int = 90
) -> list[ScanHistoryPoint]:
    """90-day score-history series for the item, oldest-first."""
    since = datetime.now().astimezone() - timedelta(days=window_days)
    rows = (
        await session.execute(
            select(Scan.scanned_at, Scan.aggregate_score, Scan.tier)
            .where(Scan.catalog_item_id == catalog_item_id)
            .where(Scan.scanned_at >= since)
            .order_by(Scan.scanned_at.asc())
        )
    ).all()
    return [
        ScanHistoryPoint(scanned_at=scanned_at, aggregate_score=score, tier=tier)  # type: ignore[arg-type]
        for scanned_at, score, tier in rows
    ]


async def _versions(
    session: AsyncSession, catalog_item_id: object, *, limit: int = 12
) -> list[VersionPoint]:
    """Version-history rail — the most-recent scans (newest first) with the
    per-scan sub_scores the diff panel needs. `tag` is null for now (release-tag
    resolution is a later refinement); the UI falls back to the short ref SHA.
    """
    rows = (
        await session.execute(
            select(Scan.ref_sha, Scan.scanned_at, Scan.aggregate_score, Scan.tier, Scan.sub_scores)
            .where(Scan.catalog_item_id == catalog_item_id)
            .order_by(desc(Scan.scanned_at))
            .limit(limit)
        )
    ).all()
    return [
        VersionPoint(
            tag=None,
            ref_sha=ref_sha,
            scanned_at=scanned_at,
            aggregate_score=score,
            tier=tier,  # type: ignore[arg-type]
            sub_scores={
                str(k): int(v) for k, v in cast("dict[str, int]", sub_scores or {}).items()
            },
        )
        for ref_sha, scanned_at, score, tier, sub_scores in rows
    ]


async def _related_items(
    session: AsyncSession, *, kind: str, exclude_id: object, limit: int = 4
) -> list[RelatedItem]:
    """Same-kind, highest-scored peers (excluding self).

    Placeholder until I-04 adds the tag/category/co-install signal.
    """
    latest_scan_sub = (
        select(
            Scan.catalog_item_id.label("ci_id"),
            Scan.aggregate_score.label("score"),
            Scan.tier.label("tier"),
            func.row_number()
            .over(partition_by=Scan.catalog_item_id, order_by=desc(Scan.scanned_at))
            .label("rn"),
        )
    ).subquery()
    rows = (
        await session.execute(
            select(
                CatalogItem.slug,
                CatalogItem.display_name,
                latest_scan_sub.c.score,
                latest_scan_sub.c.tier,
            )
            .join(latest_scan_sub, latest_scan_sub.c.ci_id == CatalogItem.id, isouter=True)
            .where(CatalogItem.kind == kind)
            .where(CatalogItem.id != exclude_id)
            .where(CatalogItem.archived.is_(False))
            .where(or_(latest_scan_sub.c.rn == 1, latest_scan_sub.c.rn.is_(None)))
            .order_by(desc(func.coalesce(latest_scan_sub.c.score, 0)), CatalogItem.slug)
            .limit(limit)
        )
    ).all()
    return [
        RelatedItem(slug=slug, display_name=name, aggregate_score=score, tier=tier)  # type: ignore[arg-type]
        for slug, name, score, tier in rows
    ]


async def _vendor_responses(session: AsyncSession, item: CatalogItem) -> list[VendorResponsePublic]:
    """Public vendor responses for the item, newest version first.

    Public author attribution is the **verified repository** (`<org>/<repo>`),
    NOT the self-reported GitHub handle the submitter typed. The
    `.saferskills/verify.txt` flow proves *control of the repo*, not the
    identity of a specific GitHub user — so attributing to a self-asserted
    handle would let a repo-controller impersonate an arbitrary `@user`.
    Identity-level verification (OAuth + push-permission) lands with auth in
    I-06; until then the repo coordinate is the only trustworthy attribution.
    """
    repo_authority = f"{item.github_org}/{item.github_repo} maintainer"
    rows = (
        (
            await session.execute(
                select(VendorResponse)
                .where(VendorResponse.catalog_item_id == item.id)
                .order_by(desc(VendorResponse.version))
            )
        )
        .scalars()
        .all()
    )
    return [
        VendorResponsePublic(
            id=str(resp.id),
            author=repo_authority,
            body_markdown=resp.body_markdown,
            submitted_at=resp.submitted_at,
            version=resp.version,
        )
        for resp in rows
    ]


@router.get("/{slug}", response_model=ItemDetailResponse)
async def get_item(slug: str, session: AsyncSession = Depends(get_session)) -> ItemDetailResponse:
    stmt = select(CatalogItem).where(CatalogItem.slug == slug)
    item = (await session.execute(stmt)).scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=404, detail="item not found")

    latest_scan_stmt = (
        select(Scan).where(Scan.catalog_item_id == item.id).order_by(desc(Scan.scanned_at)).limit(1)
    )
    latest = (await session.execute(latest_scan_stmt)).scalar_one_or_none()

    findings: Sequence[Finding] = []
    findings_count = 0
    latest_scan_detail = None
    if latest is not None:
        findings = (
            (await session.execute(select(Finding).where(Finding.scan_id == latest.id)))
            .scalars()
            .all()
        )
        findings_count = len(findings)
        latest_scan_detail = build_scan_report_detail(latest, item, findings)

    # Sub-scores of the 2nd-most-recent scan → powers the item page's per-category
    # "Δ vs last scan" column. None when the item has fewer than two scans.
    previous_sub_scores: dict[str, int] | None = None
    if latest is not None:
        prev = (
            await session.execute(
                select(Scan.sub_scores)
                .where(Scan.catalog_item_id == item.id)
                .order_by(desc(Scan.scanned_at))
                .offset(1)
                .limit(1)
            )
        ).scalar_one_or_none()
        if isinstance(prev, dict):
            previous_sub_scores = {str(k): int(v) for k, v in prev.items()}

    reg_rows = (
        await session.execute(
            select(ItemSource.registry_id).where(ItemSource.catalog_item_id == item.id)
        )
    ).all()
    registries = [r[0] for r in reg_rows]

    detail = CatalogItemDetail(
        id=str(item.id),
        slug=item.slug,
        kind=item.kind,  # type: ignore[arg-type]
        display_name=item.display_name,
        description=(
            item.item_metadata.get("description") if isinstance(item.item_metadata, dict) else None
        ),
        github_url=item.github_url,
        github_org=item.github_org,
        github_repo=item.github_repo,
        popularity_tier=item.popularity_tier,
        popularity_score=item.popularity_score,
        latest_scan_score=latest.aggregate_score if latest is not None else None,
        latest_scan_tier=latest.tier if latest is not None else None,  # type: ignore[arg-type]
        latest_scan_at=latest.scanned_at if latest is not None else None,
        findings_count=findings_count,
        registries=registries,
        updated_at=item.updated_at,
        sources=item.sources,
        item_metadata=item.item_metadata,
    )

    repo = RepoMeta(
        stars=item.github_stars,
        forks=item.github_forks,
        license_spdx=item.license_spdx,
        latest_version=item.latest_version,
        verified="vendor_verified" in registries,
    )

    manifest = None
    if latest is not None and latest.manifest_source:
        manifest = ManifestSource(
            path=latest.manifest_path or "SKILL.md",
            content=latest.manifest_source,
            bytes=len(latest.manifest_source.encode("utf-8")),
        )

    return ItemDetailResponse(
        item=detail,
        latest_scan=latest_scan_detail,
        scan_history=await _scan_history(session, item.id),
        install_activity=_mock_install_activity(item.popularity_score),
        related_items=await _related_items(session, kind=item.kind, exclude_id=item.id),
        vendor_responses=await _vendor_responses(session, item),
        previous_sub_scores=previous_sub_scores,
        repo=repo,
        versions=await _versions(session, item.id),
        manifest=manifest,
    )
