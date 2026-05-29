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
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.models.catalog_item import CatalogItem
from app.models.item_source import ItemSource
from app.models.scan import Finding, Scan
from app.models.vendor import VendorResponse, VendorVerification
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
    RelatedItem,
    ScanHistoryPoint,
    VendorResponsePublic,
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

    # Tier facet: bucket by latest_scan_tier — needs the per-item latest scan.
    latest_per_item = (
        select(Scan.catalog_item_id, func.max(Scan.scanned_at).label("max_scanned_at"))
        .group_by(Scan.catalog_item_id)
        .subquery()
    )
    tier_rows = (
        await session.execute(
            select(Scan.tier, func.count(Scan.id))
            .join(
                latest_per_item,
                and_(
                    Scan.catalog_item_id == latest_per_item.c.catalog_item_id,
                    Scan.scanned_at == latest_per_item.c.max_scanned_at,
                ),
            )
            .group_by(Scan.tier)
        )
    ).all()

    return CatalogFacets(
        kind={k: int(c) for k, c in kind_rows},
        popularity_tier={k: int(c) for k, c in popularity_rows},
        tier={k: int(c) for k, c in tier_rows},
        registry={k: int(c) for k, c in registry_rows},
        total=int(total),
    )


@router.get("", response_model=CatalogListEnvelope)
async def list_items(
    kind: list[str] | None = Query(default=None),
    score_min: int = Query(default=0, ge=0, le=100),
    score_max: int = Query(default=100, ge=0, le=100),
    scan_tier: list[str] | None = Query(default=None),
    q: str | None = Query(default=None, max_length=200),
    sort: SortKey = Query(default="most_installed"),
    limit: int = Query(default=25, ge=1, le=100),
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

    if cursor:
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

    stmt = stmt.limit(limit + 1)
    rows = (await session.execute(stmt)).all()
    has_more = len(rows) > limit
    rows = rows[:limit]

    total = (
        await session.execute(
            select(func.count(CatalogItem.id)).where(CatalogItem.archived.is_(False))
        )
    ).scalar_one()

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
        total_count=int(total),
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


async def _vendor_responses(
    session: AsyncSession, catalog_item_id: object
) -> list[VendorResponsePublic]:
    """Public vendor responses for the item, newest version first."""
    rows = (
        await session.execute(
            select(VendorResponse, VendorVerification.verified_github_user)
            .join(
                VendorVerification,
                VendorVerification.id == VendorResponse.vendor_verification_id,
            )
            .where(VendorResponse.catalog_item_id == catalog_item_id)
            .order_by(desc(VendorResponse.version))
        )
    ).all()
    return [
        VendorResponsePublic(
            id=str(resp.id),
            author=verified_user or "verified maintainer",
            body_markdown=resp.body_markdown,
            submitted_at=resp.submitted_at,
            version=resp.version,
        )
        for resp, verified_user in rows
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

    return ItemDetailResponse(
        item=detail,
        latest_scan=latest_scan_detail,
        scan_history=await _scan_history(session, item.id),
        install_activity=_mock_install_activity(item.popularity_score),
        related_items=await _related_items(session, kind=item.kind, exclude_id=item.id),
        vendor_responses=await _vendor_responses(session, item.id),
    )
