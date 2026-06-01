"""Wire types for GET /api/v1/scans/runs/<run_id> — the repo scan report.

`ScanRunReportDetail` is the consolidated repo view: the repo aggregate score, a
by-kind tally, and every discovered capability (each its own catalog item) with
an independent score + findings. Mirrors `schemas/scan-run-report.schema.json`
(which drives the generated frontend Zod/TS).
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field

from app.schemas.orm_base import OrmBaseModel
from app.schemas.scan_report_summary import ScanTier
from app.schemas.scan_submit import FindingResponse


class FindingsSummary(OrmBaseModel):
    critical: int = 0
    high: int = 0
    medium: int = 0
    low: int = 0
    info: int = 0
    total: int = 0


class CapabilityRow(OrmBaseModel):
    kind: Literal["skill", "mcp_server", "hook", "plugin", "rules"]
    name: str
    component_path: str | None = None
    aggregate_score: int = Field(..., ge=0, le=100)
    tier: ScanTier
    scan_id: str
    catalog_slug: str
    sub_scores: dict[str, int]
    findings_summary: FindingsSummary
    findings: list[FindingResponse]


class ScanRunReportDetail(OrmBaseModel):
    id: str
    github_url: str
    repo_aggregate_score: int = Field(..., ge=0, le=100)
    repo_tier: ScanTier
    kind_tally: dict[str, int]
    capability_count: int
    capabilities: list[CapabilityRow]
    scanned_at: datetime
    rubric_version: str
    engine_version: str
    latency_ms: int
    source: str
    status: Literal["pending", "running", "completed", "failed"] = "completed"
    ref_sha: str | None = None
