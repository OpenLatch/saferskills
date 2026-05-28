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
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.models.catalog_item import CatalogItem
from app.models.item_source import ItemSource
from app.models.scan import Finding, Scan
from app.schemas.catalog_summary import (
    CatalogFacets,
    CatalogItemDetail,
    CatalogItemSummary,
    CatalogListEnvelope,
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


@router.get("/{slug}", response_model=CatalogItemDetail)
async def get_item(slug: str, session: AsyncSession = Depends(get_session)) -> CatalogItemDetail:
    stmt = select(CatalogItem).where(CatalogItem.slug == slug)
    item = (await session.execute(stmt)).scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=404, detail="item not found")

    latest_scan_stmt = (
        select(Scan).where(Scan.catalog_item_id == item.id).order_by(desc(Scan.scanned_at)).limit(1)
    )
    latest = (await session.execute(latest_scan_stmt)).scalar_one_or_none()

    findings_count = 0
    if latest is not None:
        count_stmt = select(func.count(Finding.id)).where(Finding.scan_id == latest.id)
        findings_count = int((await session.execute(count_stmt)).scalar_one())

    reg_rows = (
        await session.execute(
            select(ItemSource.registry_id).where(ItemSource.catalog_item_id == item.id)
        )
    ).all()
    registries = [r[0] for r in reg_rows]

    return CatalogItemDetail(
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
