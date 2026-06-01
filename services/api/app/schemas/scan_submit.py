"""Wire types for POST /api/v1/scans + GET /api/v1/scans/<id>."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import Field

from app.schemas.orm_base import OrmBaseModel
from app.schemas.scan_report_summary import ScanTier


class ScanSubmitRequest(OrmBaseModel):
    github_url: str = Field(..., description="Public github.com repository URL.")
    rescan: bool = Field(
        default=False,
        description="If true, bypass idempotency cache and queue a new scan.",
    )


class ScanSubmitResponse(OrmBaseModel):
    id: str
    status: Literal["pending", "running", "completed", "failed"]
    cached: bool = False
    rubric_version: str
    submitted_at: datetime


class FindingResponse(OrmBaseModel):
    id: str
    rule_id: str
    severity: Literal["info", "low", "medium", "high", "critical"]
    sub_score: Literal["security", "supply_chain", "maintenance", "transparency", "community"]
    penalty: int
    status_at_scan: Literal["shadow", "active"]
    file_path: str
    line_start: int
    line_end: int | None = None
    matched_content_sha256: str
    remediation_link: str
    rubric_version: str


class ScanReportDetail(OrmBaseModel):
    id: str
    github_url: str
    slug: str
    display_name: str
    aggregate_score: int = Field(..., ge=0, le=100)
    tier: ScanTier
    sub_scores: dict[str, int]
    score_breakdown: dict[str, Any]
    findings: list[FindingResponse]
    scanned_at: datetime
    rubric_version: str
    engine_version: str
    latency_ms: int
    source: str
    status: Literal["pending", "running", "completed", "failed"] = "completed"
    ref_sha: str
    # Per-capability context (optional → no item-detail break). Populated when the
    # scan belongs to a repo scan run (one capability of several in the repo).
    component_path: str | None = None
    scan_run_id: str | None = None
