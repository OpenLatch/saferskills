"""Wire types for GET /api/v1/items + GET /api/v1/items/<slug> + GET /facets."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import Field

from app.schemas.orm_base import OrmBaseModel
from app.schemas.scan_report_summary import ScanTier

CatalogKind = Literal["skill", "mcp_server", "hook", "plugin", "rules"]


class CatalogItemSummary(OrmBaseModel):
    id: str
    slug: str
    kind: CatalogKind
    display_name: str
    description: str | None = None
    github_url: str | None = None
    # Nullable since I-3.5: uploaded artifacts have no GitHub provenance.
    github_org: str | None = None
    github_repo: str | None = None
    # I-3.5: provenance of the scanned bytes — drives the catalog UPLOAD badge.
    source_kind: Literal["github", "upload"] = "github"
    popularity_tier: str
    popularity_score: int = Field(default=0, ge=0)
    latest_scan_score: int | None = Field(default=None, ge=0, le=100)
    latest_scan_tier: ScanTier | None = None
    latest_scan_at: datetime | None = None
    findings_count: int = Field(default=0, ge=0)
    registries: list[str] = Field(default_factory=list)
    agent_compatibility: list[str] = Field(default_factory=list)
    updated_at: datetime


class CatalogItemDetail(CatalogItemSummary):
    sources: list[dict[str, Any]] = Field(default_factory=list)  # type: ignore[arg-type]
    item_metadata: dict[str, Any] | None = None


class CatalogListEnvelope(OrmBaseModel):
    data: list[CatalogItemSummary]
    next_cursor: str | None = Field(default=None)
    total_count: int = Field(default=0, ge=0)
    page: int = Field(default=1, ge=1)
    total_pages: int = Field(default=1, ge=1)
    page_size: int = Field(default=25, ge=1)


class CatalogFacets(OrmBaseModel):
    """Per-filter-option counts for the catalog filter sidebar."""

    kind: dict[str, int] = Field(default_factory=dict)
    popularity_tier: dict[str, int] = Field(default_factory=dict)
    tier: dict[str, int] = Field(default_factory=dict)
    registry: dict[str, int] = Field(default_factory=dict)
    agent: dict[str, int] = Field(default_factory=dict)
    # I-3.5: provenance split (github | upload) for the catalog source filter.
    artifact_source: dict[str, int] = Field(default_factory=dict)
    total: int = Field(default=0, ge=0)
