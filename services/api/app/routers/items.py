"""Catalog browse surface — list + detail + facets.

Reads `catalog_items` + optionally joins on the most-recent `scans` row to
project `latest_scan_score` / `latest_scan_tier` per item. Phase B supports
keyset-style cursor pagination + a small set of filters that the catalog
filter sidebar drives.
"""

from __future__ import annotations

import asyncio
import base64
import io
import logging
import zipfile
from collections.abc import Sequence
from datetime import datetime, timedelta
from typing import Literal, cast
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import and_, desc, func, or_, select, text, true
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.rate_limit import enforce_ip_rate_limit
from app.db.session import get_session
from app.models.artifact_blob import ArtifactBlob
from app.models.catalog_item import CatalogItem
from app.models.install_event import InstallEvent
from app.models.item_source import ItemSource
from app.models.scan import Finding, Scan
from app.models.vendor import VendorResponse
from app.queries import latest_scan_tier_distribution
from app.routers.scans import (
    _is_loopback,  # pyright: ignore[reportPrivateUsage]
    _peer_host,  # pyright: ignore[reportPrivateUsage]
    _rate_limit_ip,  # pyright: ignore[reportPrivateUsage]
)
from app.scan.report_builder import build_scan_report_detail
from app.schemas.catalog_summary import (
    CatalogFacets,
    CatalogItemDetail,
    CatalogItemSummary,
    CatalogListEnvelope,
)
from app.schemas.item_detail import (
    AgentShare,
    DiffFile,
    DiffHunk,
    DiffLine,
    DiffResponse,
    DownloadInfo,
    InstallActivity,
    ItemDetailResponse,
    ManifestSource,
    RelatedItem,
    RepoMeta,
    ScanHistoryPoint,
    VendorResponsePublic,
    VersionPoint,
)
from app.services.artifact_diff import diff_snapshots, load_snapshot
from app.services.finding_evidence import resolve_finding_excerpts

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/items", tags=["items"])

# Hard cap on a served snapshot zip (uncompressed total), mirrors the engine's
# 25 MiB tarball fetch cap. Over this → 413 on the anonymous download endpoint.
_MAX_ZIP_BYTES = 25 * 1024 * 1024


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
        source_kind=item.source_kind,  # type: ignore[arg-type]
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
    # Public-only catalog: unlisted shadow rows never contribute to any facet.
    total = (
        await session.execute(
            select(func.count(CatalogItem.id)).where(CatalogItem.visibility == "public")
        )
    ).scalar_one()

    kind_rows = (
        await session.execute(
            select(CatalogItem.kind, func.count(CatalogItem.id))
            .where(CatalogItem.archived.is_(False), CatalogItem.visibility == "public")
            .group_by(CatalogItem.kind)
        )
    ).all()
    popularity_rows = (
        await session.execute(
            select(CatalogItem.popularity_tier, func.count(CatalogItem.id))
            .where(CatalogItem.archived.is_(False), CatalogItem.visibility == "public")
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
    # The set-returning function references catalog_items.agent_compatibility, so
    # it must be joined as an explicit LATERAL. (`select_from(CatalogItem, fn)` —
    # a comma cross-join — relies on Postgres' implicit lateral and trips
    # SQLAlchemy's cartesian-product warning; `JOIN LATERAL ... ON true` is the
    # same INNER lateral semantics — empty/NULL arrays yield no rows — made
    # visible to the compiler.)
    agent_fn = (
        func.jsonb_array_elements_text(CatalogItem.agent_compatibility)
        .table_valued("value")
        .lateral()
    )
    agent_rows = (
        await session.execute(
            select(agent_fn.c.value, func.count(CatalogItem.id))
            .select_from(CatalogItem)
            .join(agent_fn, true())
            .where(CatalogItem.archived.is_(False), CatalogItem.visibility == "public")
            .group_by(agent_fn.c.value)
        )
    ).all()

    # Tier facet: bucket by latest_scan_tier — shared with /stats (queries.py).
    tier_dist = await latest_scan_tier_distribution(session)

    # Provenance facet (I-3.5): github | upload split for the source filter.
    source_rows = (
        await session.execute(
            select(CatalogItem.source_kind, func.count(CatalogItem.id))
            .where(CatalogItem.archived.is_(False), CatalogItem.visibility == "public")
            .group_by(CatalogItem.source_kind)
        )
    ).all()

    return CatalogFacets(
        kind={k: int(c) for k, c in kind_rows},
        popularity_tier={k: int(c) for k, c in popularity_rows},
        tier=tier_dist,
        registry={k: int(c) for k, c in registry_rows},
        agent={k: int(c) for k, c in agent_rows},
        artifact_source={k: int(c) for k, c in source_rows},
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
    artifact_source: Literal["github", "upload"] | None = Query(
        default=None,
        description=(
            "Provenance filter on the catalog item's source_kind. NOT named "
            "`source` (that is the scan TRIGGER enum) — P1-4."
        ),
    ),
    q: str | None = Query(default=None, max_length=200),
    show_low_quality: bool = Query(
        default=False,
        alias="showLowQuality",
        description="Include low/empty quality_tier items (default hides them — D-04-19).",
    ),
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
        # Public-only catalog: unlisted shadow rows are never listed (D-UP-19).
        .where(CatalogItem.archived.is_(False), CatalogItem.visibility == "public")
    )

    # Soft quality gate (D-04-19): the default catalog hides low/empty items;
    # `?showLowQuality=true` exposes them. Hidden items stay reachable by slug.
    if not show_low_quality:
        stmt = stmt.where(CatalogItem.quality_tier.in_(["high", "medium"]))

    if artifact_source:
        stmt = stmt.where(CatalogItem.source_kind == artifact_source)
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
        # Postgres FTS (search_vector tsvector, migration 0010) OR pg_trgm fuzzy
        # on display_name (D-04-32). search_vector is a DB-generated column, not a
        # mapped attribute — referenced via text() with a bound param.
        stmt = stmt.where(
            text(
                "(catalog_items.search_vector @@ websearch_to_tsquery('english', :q) "
                "OR similarity(catalog_items.display_name, :q) > 0.3)"
            ).bindparams(q=q)
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

    if q:
        # Relevance-first when searching: blend ts_rank (0.7) + normalized
        # popularity (0.3) so a strong name match isn't drowned by a popular
        # near-miss (D-04-32). Ties broken by slug for a stable keyset.
        stmt = stmt.order_by(
            text(
                "ts_rank(catalog_items.search_vector, websearch_to_tsquery('english', :q)) * 0.7 "
                "+ (catalog_items.popularity_score / 100.0) * 0.3 DESC"
            ).bindparams(q=q),
            CatalogItem.slug,
        )
    elif sort == "highest_score":
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


async def _install_activity(session: AsyncSession, catalog_item_id: object) -> InstallActivity:
    """Real opt-in install counts + agent distribution (D-05-31).

    GROUP-BY aggregate over `install_events` — replaces the deterministic mock.
    Anonymized counts ONLY (never company-level data — company intelligence is
    OpenLatch's private B2B surface, never public per `.claude/rules/security.md`).
    A capability with no reported installs returns zeros + an empty distribution.
    """
    now = datetime.now().astimezone()
    week_ago = now - timedelta(days=7)
    month_ago = now - timedelta(days=30)

    counts = (
        await session.execute(
            select(
                func.count().label("all_time"),
                func.count().filter(InstallEvent.created_at >= week_ago).label("this_week"),
                func.count().filter(InstallEvent.created_at >= month_ago).label("this_month"),
            ).where(InstallEvent.catalog_item_id == catalog_item_id)
        )
    ).one()
    all_time = int(counts.all_time)

    distribution: list[AgentShare] = []
    if all_time > 0:
        rows = (
            await session.execute(
                select(InstallEvent.agent, func.count().label("n"))
                .where(InstallEvent.catalog_item_id == catalog_item_id)
                .group_by(InstallEvent.agent)
                .order_by(func.count().desc())
            )
        ).all()
        distribution = [
            AgentShare(agent=agent, percentage=round(n / all_time * 100)) for agent, n in rows
        ]

    return InstallActivity(
        this_week=int(counts.this_week),
        this_month=int(counts.this_month),
        all_time=all_time,
        agent_distribution=distribution,
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
            select(
                Scan.id,
                Scan.ref_sha,
                Scan.scanned_at,
                Scan.aggregate_score,
                Scan.tier,
                Scan.sub_scores,
                Scan.file_hashes,
            )
            .where(Scan.catalog_item_id == catalog_item_id)
            .order_by(desc(Scan.scanned_at))
            .limit(limit)
        )
    ).all()
    return [
        VersionPoint(
            tag=None,
            scan_id=str(scan_id),
            ref_sha=ref_sha,
            scanned_at=scanned_at,
            aggregate_score=score,
            tier=tier,  # type: ignore[arg-type]
            sub_scores={
                str(k): int(v) for k, v in cast("dict[str, int]", sub_scores or {}).items()
            },
            has_snapshot=bool(file_hashes),
        )
        for scan_id, ref_sha, scanned_at, score, tier, sub_scores, file_hashes in rows
    ]


def _has_servable_snapshot(scan: Scan) -> bool:
    """True when the scan's snapshot has at least one stored (text) blob.

    `file_hashes` populated AND at least one path maps to a sha (a scan that
    captured only binaries — all-null map — has no servable content).
    """
    return bool(scan.file_hashes) and any(scan.file_hashes.values())


async def _latest_snapshot_scan(session: AsyncSession, catalog_item_id: object) -> Scan | None:
    """Most-recent scan that persisted a usable file snapshot (newest first).

    Pre-storage scans have `file_hashes IS NULL` and are skipped.
    """
    scans = (
        (
            await session.execute(
                select(Scan)
                .where(Scan.catalog_item_id == catalog_item_id)
                .where(Scan.file_hashes.isnot(None))
                .order_by(desc(Scan.scanned_at))
            )
        )
        .scalars()
        .all()
    )
    return next((scan for scan in scans if _has_servable_snapshot(scan)), None)


async def _download_info(session: AsyncSession, scan: Scan) -> DownloadInfo:
    """Build the served-zip pointer for a scan with a snapshot.

    `byte_size` is the uncompressed total served (sum over stored paths — a file
    written once per path, so deduped blobs shared by two paths count twice).
    """
    file_hashes: dict[str, str | None] = scan.file_hashes or {}
    shas = {sha for sha in file_hashes.values() if sha}
    sizes: dict[str, int] = {}
    if shas:
        rows = (
            await session.execute(
                select(ArtifactBlob.sha256, ArtifactBlob.byte_size).where(
                    ArtifactBlob.sha256.in_(shas)
                )
            )
        ).all()
        sizes = {sha: int(size) for sha, size in rows}
    total = sum(sizes.get(sha, 0) for sha in file_hashes.values() if sha)
    return DownloadInfo(scan_id=str(scan.id), byte_size=total)


async def _load_scan_for_item(session: AsyncSession, catalog_item_id: object, scan_id: str) -> Scan:
    """Load a scan that MUST belong to this item — the slug↔scan ownership gate.

    A foreign or unknown scan_id 404s (never leaks another item's scan), and a
    malformed UUID 400s.
    """
    try:
        sid = UUID(scan_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="invalid scan id") from exc
    scan = (
        await session.execute(
            select(Scan).where(Scan.id == sid).where(Scan.catalog_item_id == catalog_item_id)
        )
    ).scalar_one_or_none()
    if scan is None:
        raise HTTPException(status_code=404, detail="scan not found for this item")
    return scan


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
            .where(CatalogItem.visibility == "public")
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
    # Public-only detail: an unlisted shadow slug 404s here (reachable only via
    # its capability URL, never the public catalog surface — D-UP-19).
    stmt = select(CatalogItem).where(CatalogItem.slug == slug, CatalogItem.visibility == "public")
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
        evidence = await resolve_finding_excerpts(session, latest, findings)
        latest_scan_detail = build_scan_report_detail(latest, item, findings, evidence=evidence)

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
        source_kind=item.source_kind,  # type: ignore[arg-type]
        popularity_tier=item.popularity_tier,
        popularity_score=item.popularity_score,
        latest_scan_score=latest.aggregate_score if latest is not None else None,
        latest_scan_tier=latest.tier if latest is not None else None,  # type: ignore[arg-type]
        latest_scan_at=latest.scanned_at if latest is not None else None,
        findings_count=findings_count,
        registries=registries,
        agent_compatibility=list(item.agent_compatibility or []),
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

    download = None
    snapshot_scan = await _latest_snapshot_scan(session, item.id)
    if snapshot_scan is not None:
        download = await _download_info(session, snapshot_scan)

    return ItemDetailResponse(
        item=detail,
        latest_scan=latest_scan_detail,
        scan_history=await _scan_history(session, item.id),
        install_activity=await _install_activity(session, item.id),
        related_items=await _related_items(session, kind=item.kind, exclude_id=item.id),
        vendor_responses=await _vendor_responses(session, item),
        previous_sub_scores=previous_sub_scores,
        repo=repo,
        versions=await _versions(session, item.id),
        manifest=manifest,
        download=download,
    )


async def _require_item(session: AsyncSession, slug: str) -> CatalogItem:
    # Public-only: unlisted shadow slugs 404 on /diff + /download too (their bytes
    # are token-gated via /scans/r/<token>, never the public item surface).
    item = (
        await session.execute(
            select(CatalogItem).where(CatalogItem.slug == slug, CatalogItem.visibility == "public")
        )
    ).scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=404, detail="item not found")
    return item


def _build_zip(files: dict[str, bytes]) -> bytes:
    """Deterministic deflate zip of `{path: bytes}` — runs in a worker thread."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(files):
            archive.writestr(path, files[path])
    return buffer.getvalue()


@router.get("/{slug}/diff", response_model=DiffResponse)
async def get_item_diff(
    slug: str,
    to: str = Query(..., description="scan_id of the newer snapshot"),
    from_: str | None = Query(
        default=None, alias="from", description="scan_id of the older snapshot"
    ),
    session: AsyncSession = Depends(get_session),
) -> DiffResponse:
    """Line-level diff between two stored scan snapshots of the same item.

    Both scans must belong to `slug`; `from` defaults to the scan just older
    than `to`. 404 if either snapshot is absent (a pre-storage scan). The diff
    is CPU-bound, so it runs in a worker thread off the event loop.
    """
    item = await _require_item(session, slug)
    to_scan = await _load_scan_for_item(session, item.id, to)

    if from_ is not None:
        from_scan: Scan | None = await _load_scan_for_item(session, item.id, from_)
    else:
        from_scan = (
            await session.execute(
                select(Scan)
                .where(Scan.catalog_item_id == item.id)
                .where(Scan.scanned_at < to_scan.scanned_at)
                .order_by(desc(Scan.scanned_at))
                .limit(1)
            )
        ).scalar_one_or_none()
        if from_scan is None:
            raise HTTPException(status_code=404, detail="no prior scan to diff against")

    if not to_scan.file_hashes or not from_scan.file_hashes:
        raise HTTPException(status_code=404, detail="snapshot not available for one of these scans")

    old = await load_snapshot(session, from_scan)
    new = await load_snapshot(session, to_scan)
    result = await asyncio.to_thread(diff_snapshots, old, new)

    return DiffResponse(
        from_scan_id=str(from_scan.id),
        to_scan_id=str(to_scan.id),
        files=[
            DiffFile(
                path=f.path,
                status=f.status,  # type: ignore[arg-type]
                note=f.note,
                hunks=[
                    DiffHunk(
                        header=h.header,
                        lines=[
                            DiffLine(type=line.type, text=line.text, gutter=line.gutter)  # type: ignore[arg-type]
                            for line in h.lines
                        ],
                    )
                    for h in f.hunks
                ],
            )
            for f in result.files
        ],
        truncated=result.truncated,
    )


@router.get("/{slug}/download")
async def download_item_snapshot(
    slug: str,
    request: Request,
    scan: str | None = Query(default=None, description="scan_id; default = latest with a snapshot"),
    session: AsyncSession = Depends(get_session),
) -> StreamingResponse:
    """Serve a stored scan snapshot as a SaferSkills-built `.zip`.

    Default target is the latest scan with a snapshot. Per-IP daily rate cap
    (loopback-exempt, cf. `scans.py::_is_loopback`) + a snapshot-size cap guard
    the anonymous endpoint. Snapshots are immutable → far-future `Cache-Control`.
    """
    settings = get_settings()
    item = await _require_item(session, slug)

    if scan is not None:
        target = await _load_scan_for_item(session, item.id, scan)
    else:
        latest_snapshot = await _latest_snapshot_scan(session, item.id)
        if latest_snapshot is None:
            raise HTTPException(status_code=404, detail="no stored snapshot for this item")
        target = latest_snapshot

    if not _has_servable_snapshot(target):
        raise HTTPException(status_code=404, detail="snapshot not available for this scan")

    if not _is_loopback(_peer_host(request)):
        await enforce_ip_rate_limit(
            session,
            ip=_rate_limit_ip(request, settings),
            bucket="artifact_download",
            limit=settings.artifact_download_daily_limit,
        )

    snapshot = await load_snapshot(session, target)
    files = {path: content for path, content in snapshot.items() if content is not None}
    total = sum(len(content) for content in files.values())
    if total > _MAX_ZIP_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"snapshot exceeds the {_MAX_ZIP_BYTES} byte download cap",
        )

    payload = await asyncio.to_thread(_build_zip, files)
    filename = f"{slug}.zip"
    disposition = f"attachment; filename=\"{filename}\"; filename*=UTF-8''{quote(filename)}"
    return StreamingResponse(
        io.BytesIO(payload),
        media_type="application/zip",
        headers={
            "Content-Disposition": disposition,
            "Cache-Control": "public, max-age=31536000, immutable",
            "Content-Length": str(len(payload)),
        },
    )
