"""Wire types for GET /api/v1/items/<slug> — the item-detail surface.

Phase C extends the W1 catalog-detail projection (`CatalogItemDetail`) with the
data the item-detail page (`/items/<slug>`) renders beyond the bare catalog row:
the full latest scan report, a 90-day score-history series, anonymized install
activity, and a related-items grid.

These are hand-written endpoint DTOs (non-generated wrappers around the
generated entity shapes), per `.claude/rules/schema-driven-development.md`
§ "Adding a new endpoint DTO". `pnpm run generate` picks them up via
`app.openapi()` → `openapi.json` → the TS DTO generator.

`install_activity` is anonymized counts ONLY — never company-level data
(company intelligence is OpenLatch's private B2B surface, never public). At
I-03 ship the values are deterministic placeholders derived from the catalog
item's popularity_score; I-05 (Install CLI) wires real install telemetry.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from app.schemas.catalog_summary import CatalogItemDetail
from app.schemas.orm_base import OrmBaseModel
from app.schemas.scan_report_summary import ScanTier
from app.schemas.scan_submit import ScanReportDetail


class ScanHistoryPoint(OrmBaseModel):
    """One point on the 90-day score-history line."""

    scanned_at: datetime
    aggregate_score: int = Field(..., ge=0, le=100)
    tier: ScanTier


class AgentShare(OrmBaseModel):
    """One slice of the install agent-distribution row."""

    agent: str
    percentage: int = Field(..., ge=0, le=100)


class InstallActivity(OrmBaseModel):
    """Anonymized install counts + agent distribution. No company-level data."""

    this_week: int = Field(default=0, ge=0)
    this_month: int = Field(default=0, ge=0)
    all_time: int = Field(default=0, ge=0)
    agent_distribution: list[AgentShare]


class RelatedItem(OrmBaseModel):
    """One card in the related-items grid."""

    slug: str
    display_name: str
    aggregate_score: int | None = Field(default=None, ge=0, le=100)
    tier: ScanTier | None = None


class VendorResponsePublic(OrmBaseModel):
    """A verified-vendor public response, surfaced next to findings."""

    id: str
    author: str
    body_markdown: str
    submitted_at: datetime
    version: int


class ItemDetailResponse(OrmBaseModel):
    """Full payload for the item-detail page."""

    item: CatalogItemDetail
    latest_scan: ScanReportDetail | None = None
    scan_history: list[ScanHistoryPoint]
    install_activity: InstallActivity
    related_items: list[RelatedItem]
    vendor_responses: list[VendorResponsePublic]
