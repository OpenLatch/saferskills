"""PHASE A2 PLACEHOLDER — replaced whole-cloth by Phase B routers/scans.py.

Read-only stub of GET /api/v1/scans that projects the data-seed catalog
fixture (tools/data-seed/.../catalog.yaml) into the ScanReportSummary shape
the webapp expects, so the homepage feeds render real data at W1 before
Phase B ships the real scan engine.

Phase B (D-FE-34) replaces this with the DB-backed scan router. The shape
of the response (ListEnvelope with snake_case keys) is intentionally
identical to what Phase B will ship.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal, cast

import yaml
from fastapi import APIRouter, Query
from pydantic import Field

from app.schemas.orm_base import OrmBaseModel

router = APIRouter(tags=["scans-stub"])


ScanTier = Literal["green", "yellow", "orange", "red", "unscoped"]


class ScanReportSummary(OrmBaseModel):
    id: str
    github_url: str
    slug: str
    aggregate_score: int
    tier: ScanTier
    scanned_at: str
    findings_count: int = 0
    author: str | None = None
    title: str | None = None


class ListEnvelope(OrmBaseModel):
    data: list[ScanReportSummary]
    next_cursor: str | None = Field(default=None)


_CATALOG_PATH = (
    Path(__file__).resolve().parents[4]
    / "tools"
    / "data-seed"
    / "saferskills_data_seed"
    / "domains"
    / "catalog"
    / "files"
    / "catalog.yaml"
)


def _tier_for(score: int) -> ScanTier:
    if score >= 80:
        return "green"
    if score >= 60:
        return "yellow"
    if score >= 40:
        return "orange"
    return "red"


def _author_from_slug(slug: str) -> str:
    return slug.split("--", 1)[0] if "--" in slug else "unknown"


CatalogItem = dict[str, Any]


def _load_catalog() -> list[CatalogItem]:
    if not _CATALOG_PATH.exists():
        return []
    try:
        with _CATALOG_PATH.open("r", encoding="utf-8") as fh:
            doc = cast(dict[str, Any], yaml.safe_load(fh) or {})
    except OSError, yaml.YAMLError:
        return []
    raw_items: object = doc.get("items") or []
    if not isinstance(raw_items, list):
        return []
    return [
        cast(CatalogItem, item) for item in cast(list[object], raw_items) if isinstance(item, dict)
    ]


def _project(item: CatalogItem, minutes_ago: int) -> ScanReportSummary:
    score = int(item.get("expected_score", 0))
    now = datetime.now(UTC)
    scanned_at = (now - timedelta(minutes=minutes_ago)).isoformat()
    slug = str(item.get("slug", ""))
    findings = max(0, int((100 - score) / 20))
    return ScanReportSummary(
        id=slug,
        github_url=str(item.get("github_url", "")),
        slug=slug,
        aggregate_score=score,
        tier=_tier_for(score),
        scanned_at=scanned_at,
        findings_count=findings,
        author=_author_from_slug(slug),
        title=str(item.get("display_name", slug)),
    )


@router.get(
    "/scans",
    response_model=ListEnvelope,
    summary="List recent scans (Phase A2 placeholder)",
)
async def list_scans(
    source: str | None = Query(default=None),
    limit: int = Query(default=10, ge=1, le=50),
    order: str | None = Query(default=None),
) -> ListEnvelope:
    _ = source, order
    items = _load_catalog()
    if not items:
        return ListEnvelope(data=[])

    items = items[:limit]
    data = [_project(item, minutes_ago=2 + i * 3) for i, item in enumerate(items)]
    return ListEnvelope(data=data)
