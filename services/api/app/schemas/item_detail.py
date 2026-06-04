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
from typing import Literal

from pydantic import Field

from app.schemas.catalog_summary import CatalogItemDetail
from app.schemas.orm_base import OrmBaseModel
from app.schemas.scan_report_summary import ScanTier
from app.schemas.scan_submit import ScanReportDetail
from app.services.agent_compat import AgentName


class ScanHistoryPoint(OrmBaseModel):
    """One point on the 90-day score-history line."""

    scanned_at: datetime
    aggregate_score: int = Field(..., ge=0, le=100)
    tier: ScanTier


class VersionPoint(OrmBaseModel):
    """One entry in the item's version-history rail (a scanned point in time).

    `tag` is the GitHub release tag when resolvable, else null (the UI falls back
    to the short ref SHA). `sub_scores` powers the per-category diff vs the
    adjacent version. `scan_id` keys the on-demand `/diff` + `/download`
    endpoints (ref_sha is NOT unique per item — a re-scan under a new
    rubric_version reuses the SHA). `has_snapshot` is true only when this scan
    persisted a file snapshot (pre-storage scans have none).
    """

    tag: str | None = None
    scan_id: str
    ref_sha: str | None = None
    scanned_at: datetime
    aggregate_score: int = Field(..., ge=0, le=100)
    tier: ScanTier
    sub_scores: dict[str, int] = Field(default_factory=dict)
    has_snapshot: bool = False


class DiffLine(OrmBaseModel):
    """One rendered line of a unified diff."""

    type: Literal["add", "del", "ctx"]
    text: str
    gutter: str = ""


class DiffHunk(OrmBaseModel):
    """A contiguous `@@ … @@` block of diff lines."""

    header: str
    # Required (the router always supplies the list) — keeps the field type
    # fully known under pyright strict, unlike a bare `default_factory=list`.
    lines: list[DiffLine]


class DiffFile(OrmBaseModel):
    """Per-file diff entry. `note` is set (and `hunks` empty) for binary /
    not-stored / collapsed-oversize files that carry no renderable line body."""

    path: str
    status: Literal["added", "removed", "modified", "binary"]
    hunks: list[DiffHunk]
    note: str | None = None


class DiffResponse(OrmBaseModel):
    """Line-level diff between two stored scan snapshots (HEAD-over-time)."""

    from_scan_id: str
    to_scan_id: str
    files: list[DiffFile]
    truncated: bool = False


class DownloadInfo(OrmBaseModel):
    """Pointer to the latest scan whose stored snapshot can be served as a zip.

    Null on the item-detail response when no scan has a snapshot yet (the UI
    falls back to the GitHub zipball). `byte_size` is the total stored snapshot
    size, surfaced as the real download size in the install card.
    """

    scan_id: str
    byte_size: int = Field(default=0, ge=0)


class ManifestSource(OrmBaseModel):
    """The primary public manifest file (SKILL.md / README) for the Source tab."""

    path: str
    content: str
    bytes: int = Field(default=0, ge=0)


class RepoMeta(OrmBaseModel):
    """Public GitHub facts mirrored onto the item header + Package card."""

    stars: int | None = None
    forks: int | None = None
    license_spdx: str | None = None
    latest_version: str | None = None
    verified: bool = False


class AgentShare(OrmBaseModel):
    """One slice of the install agent-distribution row.

    `agent` is the canonical agent id (the 8-agent closed enum, D-05-14) — no
    longer a free string now that real install telemetry (D-05-31) populates it.
    """

    agent: AgentName
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
    # Sub-scores of the 2nd-most-recent scan, so the item page can render a real
    # per-category "Δ vs last scan" column. None when the item has < 2 scans.
    previous_sub_scores: dict[str, int] | None = None
    # GitHub repository facts (header + Package card).
    repo: RepoMeta = Field(default_factory=RepoMeta)
    # Version-history rail (newest first); each carries sub_scores for diffing.
    versions: list[VersionPoint] = Field(default_factory=list[VersionPoint])
    # Primary manifest for the Source tab (null until captured at scan time).
    manifest: ManifestSource | None = None
    # Latest scan with a stored snapshot → served-zip pointer (null until one
    # exists; the install card falls back to the GitHub zipball).
    download: DownloadInfo | None = None
