"""Wire types for POST /api/v1/scans + GET /api/v1/scans/<id>."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import Field

from app.schemas.orm_base import OrmBaseModel
from app.schemas.rule_prose import RuleRemediation
from app.schemas.scan_report_summary import ScanTier


class ScanSubmitRequest(OrmBaseModel):
    github_url: str = Field(..., description="Public github.com repository URL.")
    rescan: bool = Field(
        default=False,
        description="If true, bypass idempotency cache and queue a new scan.",
    )
    visibility: Literal["public", "unlisted"] = Field(
        default="public",
        description=(
            "Listing posture. `public` (default) caches + appears in the catalog; "
            "`unlisted` never caches (nonce-salted), mints a share token, and is "
            "reachable only via its capability URL (I-3.5)."
        ),
    )


class ScanSubmitResponse(OrmBaseModel):
    id: str
    status: Literal["pending", "running", "completed", "failed"]
    cached: bool = False
    rubric_version: str
    submitted_at: datetime
    # Present (non-null) only when the submission was `unlisted`.
    share_url: str | None = None


class ScanUploadResponse(OrmBaseModel):
    """202 result of POST /api/v1/scans/upload (D-UP-06).

    `slug` is populated once known for a public upload (or omitted until the run
    completes — the FE polls the run report). `share_url` is the capability URL,
    present ONLY for an unlisted upload.
    """

    id: str
    status: Literal["pending", "running", "completed", "failed"]
    source_kind: Literal["github", "upload"] = "upload"
    visibility: Literal["public", "unlisted"]
    slug: str | None = None
    share_url: str | None = None


class CliChallengeResponse(OrmBaseModel):
    """`GET /api/v1/scans/cli-challenge` — a fresh stateless PoW challenge for the
    install CLI (D-05-30). The CLI solves it offline and replays it in the
    `X-SaferSkills-CLI-PoW` header on its next scan-submit."""

    challenge: str
    difficulty: int
    expires_at: datetime


class EvidenceLine(OrmBaseModel):
    """One line of a finding's matched-line window (mirrors the `.ex-line` markup)."""

    line_no: int
    text: str
    hit: bool


class EvidenceExcerpt(OrmBaseModel):
    """Report-DTO-only matched-line window resolved from the stored snapshot.

    Verbatim bytes (invisible chars preserved — the client reveals them). This is
    NOT a scan-trace field and is NOT persisted on the `findings` table; the trace
    stays hash-only per security.md § Scan-trace transparency. The bytes come from
    the stored public snapshot / token-gated unlisted store, carried only on the
    report response.
    """

    file: str
    lang: str | None = None
    truncated: bool = False
    lines: list[EvidenceLine]


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
    # Report-DTO-only: the matched-line window for the explainable FindingDetail
    # card. Null when snapshot bytes are absent (binary / oversize / expired).
    evidence_excerpt: EvidenceExcerpt | None = None
    # Report-DTO-only explainable-finding prose, inlined server-side from the
    # generated rule-content map (D-05-32 reversed — the CLI renders straight from
    # the report, never fetches the rule corpus). All None when the rule_id has no
    # content entry; the finding still renders with rule_id + remediation_link.
    title: str | None = None
    explanation: str | None = None
    category_label: str | None = None
    severity_rationale: str | None = None
    remediation: RuleRemediation | None = None


class ScanReportDetail(OrmBaseModel):
    id: str
    github_url: str | None = None
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
    ref_sha: str | None = None
    # Per-capability context (optional → no item-detail break). Populated when the
    # scan belongs to a repo scan run (one capability of several in the repo).
    component_path: str | None = None
    scan_run_id: str | None = None
    # Per-capability install descriptor the `saferskills` CLI consumes to
    # install/uninstall/update this capability across compatible agents. Null for
    # kinds with no config (skill) + pre-feature scans. Snapshot-tier (already-public
    # bytes); NEVER a scan-trace field. See app/scan/discovery.py::build_install_spec.
    install_spec: dict[str, Any] | None = None
