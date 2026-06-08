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

from app.schemas.item_detail import DownloadInfo, ManifestSource
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
    # Per-capability rich-report extras (I-3.5 multi-file upload tabs). Each
    # capability carries its own primary manifest (Source tab) + `.zip` pointer
    # so a multi-file upload renders one rich report per file. Null for repo-scan
    # capabilities (the cap-table body has no per-row source viewer).
    manifest: ManifestSource | None = None
    download: DownloadInfo | None = None
    # sha256 of this capability's own primary file (the fanned-out upload file),
    # so each per-file tab shows its own provenance hash. Null when the capability
    # has no single primary file (binary / whole-repo).
    content_hash: str | None = None


class ScanRunReportDetail(OrmBaseModel):
    id: str
    github_url: str | None = None
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
    # Upload / visibility provenance (I-3.5). `share_url` is populated ONLY when the
    # report is served via the unlisted `/scans/r/<token>` route — never in a list.
    visibility: Literal["public", "unlisted"] = "public"
    source_kind: Literal["github", "upload"] = "github"
    artifact_sha256: str | None = None
    uploaded_filename: str | None = None
    expires_at: datetime | None = None
    share_url: str | None = None
    # The canonical public report URL on the webapp, built from `public_base_url`
    # (`/scans/<run_id>` for a public run, the `/scans/r/<token>` capability URL
    # for an unlisted one). Lets a client — the CLI especially — link to the real
    # report page without knowing the webapp origin, which differs from the API
    # origin in local dev (API :8000 vs webapp :4321).
    report_url: str | None = None
    # Single-capability runs (typically uploads) carry the primary manifest + a
    # `.zip` pointer so the rich upload report (mockups 3/4) renders the source
    # viewer + download. Null on multi-capability runs (the cap-list body has no
    # single source). `manifest`/`download` are detail-only — never in a list.
    manifest: ManifestSource | None = None
    download: DownloadInfo | None = None


class PromotedItem(OrmBaseModel):
    """One capability promoted from unlisted → public (D-UP-31)."""

    slug: str
    kind: Literal["skill", "mcp_server", "hook", "plugin", "rules"]
    display_name: str
    merged: bool = False


class PromoteRunResponse(OrmBaseModel):
    """Structured 200 result of POST /scans/r/<token>/promote — never a 301.

    `promoted` is True on the first (effective) promote, False on an idempotent
    re-promote of an already-public run.
    """

    promoted: bool
    run_id: str
    visibility: Literal["public", "unlisted"]
    items: list[PromotedItem]
