"""Hand-written endpoint DTOs for the agent-scan run-lifecycle router (I-5.5).

Non-generated wrappers around the generated `AgentScanReport` entity shape
(allowed at this layer per `schema-driven-development.md`). All inherit
`OrmBaseModel` -> snake_case wire keys.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import Field

from app.schemas.orm_base import OrmBaseModel
from app.services.agent_compat import AgentName

# Runtime = the canonical agent set (`agent_compat.AgentName`, the maintained
# single source - do NOT re-list the agents here) plus `other` for an unrecognized
# harness. Local Literals for the rest mirror the schema enums (the generated
# equivalents are StrEnum classes, awkward to default + assign in a wire DTO).
_Runtime = AgentName | Literal["other"]
_Visibility = Literal["public", "unlisted"]
_Severity = Literal["info", "low", "medium", "high", "critical"]
_Verdict = Literal["vulnerable", "not_observed", "n_a", "error"]
_DetectionRule = Literal[
    "substring", "normalized_substring", "transform", "tool_arg", "forbidden_tool_presence"
]
_Tier = Literal["green", "yellow", "orange", "red", "unscoped"]


class AgentScanCreateRequest(OrmBaseModel):
    """`POST /api/v1/agent-scans` body - mint a run + one-time submit token."""

    agent_name: str = Field(..., max_length=200, description="Display name for the scanned agent.")
    runtime: _Runtime = Field(..., description="Declared agent runtime (8 ids + `other`).")
    visibility: _Visibility = Field(default="public", description="public (default) | unlisted.")


class AgentScanCreateResponse(OrmBaseModel):
    """`POST /api/v1/agent-scans` 201 response."""

    run_id: UUID
    submit_token: str = Field(..., description="One-time token gating pack-fetch + submit.")
    pack_url: str = Field(..., description="Relative URL of the token-gated signed pack.")
    expires_at: datetime | None = Field(None, description="Unlisted-run TTL; null for public.")
    share_token: str | None = Field(
        None, description="Unlisted capability-URL token; null for public."
    )


class AgentScanStatusResponse(OrmBaseModel):
    """`GET /api/v1/agent-scans/{run_id}/status` token-authed lightweight poll."""

    status: str
    score: int | None = None
    band: str | None = None
    report_url: str | None = None
    share_url: str | None = None


# ── Submission contract (`agent_scan_result.v1`) ────────────────────────────────
# Transient request input (stored raw in `agent_evidence`, NOT a generated entity).
# Version-literal-gated so a v2 lands as a new discriminated variant later. NO
# verdict/score field - the cloud decides (prime invariant #1). OrmBaseModel accepts
# both snake_case and camelCase input (`populate_by_name=True`).


class AgentScanTurn(OrmBaseModel):
    """One transcript turn. `untrusted_input` carries the planted canary by
    construction - the grader matches ONLY against `agent` (+ `tool`) turns so the
    injection payload itself never counts as a leak."""

    role: Literal["untrusted_input", "agent", "tool"]
    raw_response: str


class AgentScanToolCall(OrmBaseModel):
    """A structured mock-tool call the agent made (name + args), recorded verbatim."""

    name: str
    args: dict[str, Any] = Field(default_factory=dict)


class AgentScanTestResult(OrmBaseModel):
    """The per-test evidence the client submits. `executed` is graded; the two
    non-executed states map to `n_a`/`error` (confidence-, never a penalty)."""

    test_id: str = Field(..., pattern=r"^AS-\d{2}$")
    status: Literal["executed", "skipped_capability_absent", "error"]
    turns: list[AgentScanTurn] = Field(default_factory=list[AgentScanTurn])
    tool_calls: list[AgentScanToolCall] = Field(default_factory=list[AgentScanToolCall])


class AgentScanResultV1(OrmBaseModel):
    """`POST /agent-scans/{run_id}/submit` JSON body - the raw evidence bundle."""

    schema_version: Literal["agent_scan_result.v1"]
    run_id: str
    pack_id: str
    pack_version: str
    pack_signature_verified: bool = False
    install_path: str | None = None
    capabilities_present: list[str] = Field(default_factory=list)
    capabilities_absent: list[str] = Field(default_factory=list)
    decoy_canaries_observed: list[str] = Field(default_factory=list)
    tests: list[AgentScanTestResult]


class AgentScanPasteBackRequest(OrmBaseModel):
    """Alternate submit body: a single `paste_back` blob = `base64url(gzip(json))`
    (D-5.5-17). Decoded + ratio-guarded server-side, then parsed as `AgentScanResultV1`."""

    paste_back: str = Field(..., description="base64url(gzip(agent_scan_result.v1 JSON)).")


# ── Report wire DTO (hand-written snake_case, mirrors agent-scan-report.schema) ──
# Follows the `ScanRunReportDetail` convention: a hand-written snake_case wrapper
# (no camelCase aliases) so openapi.json + the hey-api TS types stay snake_case.
# The generated `AgentScanReport` entity drives the frontend Zod/TS off the schema;
# this is the endpoint wire shape. Phase 1 never grades, so `checks`/`findings`/
# `component_scores` are always empty; Phase 2 populates them.


class AgentSaferPattern(OrmBaseModel):
    before: str
    after: str


class AgentRemediation(OrmBaseModel):
    action: str
    steps: list[str] | None = None
    safer_pattern: AgentSaferPattern | None = None


class AgentCheckRow(OrmBaseModel):
    test_id: str
    family: str
    title: str
    verdict: _Verdict
    severity: _Severity


class AgentComponentScoreRow(OrmBaseModel):
    kind: Literal["skill", "mcp_server", "hook", "plugin", "rules"]
    name: str
    path: str | None = None
    score: int = Field(..., ge=0, le=100)
    tier: _Tier
    slug: str


class AgentFindingRow(OrmBaseModel):
    id: str
    test_id: str
    severity: _Severity
    verdict: _Verdict
    family: str
    owasp_refs: list[str] = Field(default_factory=list)
    atlas_refs: list[str] = Field(default_factory=list)
    nist_refs: list[str] = Field(default_factory=list)
    score_delta: int = Field(..., le=0)
    detection_rule: _DetectionRule
    leaked_canary_slot: str | None = None
    title: str
    explanation: str
    severity_rationale: str | None = None
    category_label: str | None = None
    remediation: AgentRemediation
    # Report-DTO-only post-redaction transcript window; null on the public projection.
    evidence_excerpt: dict[str, Any] | None = None


class AgentScanReportDetail(OrmBaseModel):
    """`GET /agent-scans/{run_id}` + `.../r/{token}` wire report (snake_case)."""

    id: str
    status: str
    agent_name: str
    runtime: str
    score: int | None = None
    band: _Tier
    verdict_label: str | None = None
    cap_callout: str | None = None
    confidence: Literal["high", "medium", "low"] | None = None
    score_breakdown: dict[str, Any] | None = None
    trust_labels: list[str] = Field(default_factory=list)
    pack_id: str
    pack_version: str
    pack_signature_verified: bool | None = None
    capabilities_present: list[str] = Field(default_factory=list)
    capabilities_absent: list[str] = Field(default_factory=list)
    family_tally: dict[str, int] = Field(default_factory=dict)
    # Always supplied by the report builder (empty in Phase 1 - no grading yet).
    checks: list[AgentCheckRow]
    findings: list[AgentFindingRow]
    component_scores: list[AgentComponentScoreRow]
    visibility: _Visibility
    expires_at: datetime | None = None
    share_url: str | None = None
    report_url: str | None = None
    rubric_version: str
    engine_version: str
    latency_ms: int
    scanned_at: datetime | None = None
