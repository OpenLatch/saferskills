"""Hand-written endpoint DTOs for the agent-scan run-lifecycle router.

Non-generated wrappers around the generated `AgentScanReport` entity shape
(allowed at this layer per `schema-driven-development.md`). All inherit
`OrmBaseModel` -> snake_case wire keys.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, cast
from uuid import UUID

from pydantic import Field, field_validator

from app.schemas.orm_base import OrmBaseModel
from app.services.agent_compat import AgentName

# The `/agents` dossier capability stack (`directory._capability_tally`) reads these
# exact keys. The CLI enumerates kinds as skill/mcp_server/hook/rules/plugin, so a
# submitted tally folds `mcp_server` -> `mcp` (the directory has no `mcp_server`).
_KIND_TALLY_KEYS = frozenset({"skill", "hook", "mcp", "plugin", "rules"})


def _coerce_count(value: Any) -> int | None:
    """A best-effort non-negative-able int from a raw JSON tally value (no excepts —
    `int(...)` parsing is replaced with explicit checks so a malformed value is
    simply dropped, never raised)."""
    if isinstance(value, bool):  # bool is an int subclass — count True/False as 1/0
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str) and value.strip().lstrip("-").isdigit():
        return int(value.strip())
    return None


def _normalize_kind_tally(value: Any) -> dict[str, int] | None:
    """Fold a (best-effort, CLI-supplied) per-kind tally onto the directory key set.

    Maps `mcp_server` -> `mcp` (summing if both are present), drops unknown keys,
    and coerces every count to a non-negative int. A non-dict / empty tally -> None.
    Lenient by construction (mode='before'): a malformed tally never 422s the mint.
    """
    if not isinstance(value, dict):
        return None
    raw = cast("dict[Any, Any]", value)
    out: dict[str, int] = {}
    for raw_key, raw_count in raw.items():
        key = "mcp" if raw_key == "mcp_server" else str(raw_key)
        if key not in _KIND_TALLY_KEYS:
            continue
        count = _coerce_count(raw_count)
        if count is None:
            continue
        out[key] = out.get(key, 0) + max(0, count)
    return out or None


# Runtime = the canonical agent set (`agent_compat.AgentName`, the maintained
# single source - do NOT re-list the agents here) plus `other` for an unrecognized
# harness. Local Literals for the rest mirror the schema enums (the generated
# equivalents are StrEnum classes, awkward to default + assign in a wire DTO).
_Runtime = AgentName | Literal["other"]
# Bootstrap target platform = the 8 canonical agent ids (`agent_compat.AgentName`)
# plus `universal` (the platform-agnostic fallback template). NOT re-listed here.
_Platform = AgentName | Literal["universal"]
_Visibility = Literal["public", "unlisted"]
_Severity = Literal["info", "low", "medium", "high", "critical"]
_Verdict = Literal["vulnerable", "not_observed", "n_a", "error"]
_DetectionRule = Literal[
    "substring", "normalized_substring", "transform", "tool_arg", "forbidden_tool_presence"
]
_Tier = Literal["green", "yellow", "orange", "red", "unscoped"]


class AgentScanCreateRequest(OrmBaseModel):
    """`POST /api/v1/agent-scans` body - mint a run + one-time submit token."""

    agent_name: str | None = Field(
        default=None,
        max_length=200,
        description="Display name for the scanned agent; omit for a generated codename.",
    )
    runtime: _Runtime = Field(..., description="Declared agent runtime (8 ids + `other`).")
    visibility: _Visibility = Field(default="public", description="public (default) | unlisted.")
    component_scan_run_id: UUID | None = Field(
        default=None,
        description="Best-effort CLI-captured component scan_run id (the local-capability "
        "scan whose per-capability scores feed the Component Scores tab). Null on web paths.",
    )
    kind_tally: dict[str, int] | None = Field(
        default=None,
        description="Per-kind capability inventory (skill/mcp/hook/plugin/rules -> count) "
        "backing the /agents dossier icons. Null on web paths.",
    )

    @field_validator("kind_tally", mode="before")
    @classmethod
    def _norm_kind_tally(cls, v: Any) -> dict[str, int] | None:
        return _normalize_kind_tally(v)


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


class AgentScanBootstrapRequest(OrmBaseModel):
    """`POST|GET /api/v1/agent-scans/bootstrap` input - mint a run + return the
    platform-picked bootstrap prompt."""

    platform: _Platform = Field(
        ..., description="Target platform template (8 agent ids + `universal` fallback)."
    )
    agent_name: str | None = Field(
        default=None,
        max_length=200,
        description="Display name for the scanned agent; omit for a generated codename.",
    )
    runtime: _Runtime = Field(
        default="other", description="Declared agent runtime (8 ids + `other`)."
    )
    visibility: _Visibility = Field(default="public", description="public (default) | unlisted.")
    component_scan_run_id: UUID | None = Field(
        default=None,
        description="Best-effort CLI-captured component scan_run id (the local-capability "
        "scan whose per-capability scores feed the Component Scores tab). Null on web paths.",
    )
    kind_tally: dict[str, int] | None = Field(
        default=None,
        description="Per-kind capability inventory (skill/mcp/hook/plugin/rules -> count) "
        "backing the /agents dossier icons. Null on web paths.",
    )

    @field_validator("kind_tally", mode="before")
    @classmethod
    def _norm_kind_tally(cls, v: Any) -> dict[str, int] | None:
        return _normalize_kind_tally(v)


class AgentScanBootstrapResponse(OrmBaseModel):
    """`POST|GET /api/v1/agent-scans/bootstrap` response - the minted run + the
    rendered bootstrap prompt the agent runs (canaries are NOT in it)."""

    run_id: UUID
    prompt: str = Field(..., description="The rendered platform bootstrap prompt (no canaries).")
    consent_notice: str = Field(..., description="Company-level telemetry notice + opt-out.")
    pack_url: str = Field(..., description="Absolute URL of the token-gated signed pack.")
    submit_token: str = Field(..., description="One-time token gating pack-fetch + submit.")
    poll_url: str = Field(
        ..., description="Absolute token-authed status-poll URL (public + unlisted)."
    )
    share_token: str | None = Field(
        None, description="Unlisted capability-URL token; null for public."
    )


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
    """Alternate submit body: a single `paste_back` blob = `base64url(gzip(json))`.
    Decoded + ratio-guarded server-side, then parsed as `AgentScanResultV1`."""

    paste_back: str = Field(..., description="base64url(gzip(agent_scan_result.v1 JSON)).")


# ── Report wire DTO (hand-written snake_case, mirrors agent-scan-report.schema) ──
# Follows the `ScanRunReportDetail` convention: a hand-written snake_case wrapper
# (no camelCase aliases) so openapi.json + the hey-api TS types stay snake_case.
# The generated `AgentScanReport` entity drives the frontend Zod/TS off the schema;
# this is the endpoint wire shape. Before grading is wired, `checks`/`findings`/
# `component_scores` are always empty; the grader populates them.


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
    # Always supplied by the report builder (empty until grading is wired).
    checks: list[AgentCheckRow]
    findings: list[AgentFindingRow]
    component_scores: list[AgentComponentScoreRow]
    # When set (unlisted runs only), every Component-Scores row deep-links here (the
    # unlisted component scan_run's `/scans/r/<token>` report) instead of `/items/
    # <slug>` — the per-capability shadow items 404 on the public catalog. Null for
    # public runs (rows link to their real `/items/<slug>`).
    component_report_url: str | None = None
    visibility: _Visibility
    expires_at: datetime | None = None
    share_url: str | None = None
    report_url: str | None = None
    rubric_version: str
    engine_version: str
    latency_ms: int
    scanned_at: datetime | None = None
    # Capability-token holder's public right-of-reply (≤500 chars). Persisted on the
    # run, rendered read-only on the report; null when no reply was attached.
    vendor_reply: str | None = None
    vendor_reply_at: datetime | None = None


# ── Directory list + aggregate-stats ────────────────────────────────────────────
# Hand-written summary + envelope + aggregate models for the `/agents` directory.
# Same OrmBaseModel + `data`-envelope convention as the catalog list. PUBLIC-ONLY:
# the list query hard-filters `visibility='public' AND status IN (graded,published)
# AND score IS NOT NULL` (the report carries no transcript here either).


class AgentFindingsSummary(OrmBaseModel):
    """Per-run finding counts for a dossier card (derived from `agent_findings`)."""

    critical: int = Field(default=0, ge=0)
    high: int = Field(default=0, ge=0)
    info: int = Field(default=0, ge=0)
    total: int = Field(default=0, ge=0)


class AgentCapabilityTally(OrmBaseModel):
    """Per-kind capability counts (stored per-run on `agent_runs.kind_tally`;
    populated by the seed today, by the grader/submit flow when the component
    inventory is captured)."""

    skill: int = Field(default=0, ge=0)
    hook: int = Field(default=0, ge=0)
    mcp: int = Field(default=0, ge=0)
    plugin: int = Field(default=0, ge=0)
    rules: int = Field(default=0, ge=0)


class AgentScanSummary(OrmBaseModel):
    """One `/agents` directory dossier row (a public, graded agent run)."""

    id: str
    agent_name: str
    runtime: str
    score: int | None = Field(default=None, ge=0, le=100)
    band: _Tier
    visibility: Literal["public"] = "public"
    report_url: str | None = None
    scanned_at: datetime | None = None
    capability_tally: AgentCapabilityTally = Field(default_factory=AgentCapabilityTally)
    findings_summary: AgentFindingsSummary = Field(default_factory=AgentFindingsSummary)
    trust_tier: str | None = None


class AgentScanListEnvelope(OrmBaseModel):
    """`GET /api/v1/agent-scans` paginated envelope (`data`, never `items`)."""

    data: list[AgentScanSummary]
    total_count: int = Field(default=0, ge=0)
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=24, ge=1)
    total_pages: int = Field(default=1, ge=1)


class AgentBandShare(OrmBaseModel):
    """One band's slice of the corpus risk thermometer."""

    pct: float = Field(default=0.0, ge=0)
    count: int = Field(default=0, ge=0)


class AgentBandDistribution(OrmBaseModel):
    """Risk-distribution thermometer segments (proportions + counts)."""

    red: AgentBandShare = Field(default_factory=AgentBandShare)
    orange: AgentBandShare = Field(default_factory=AgentBandShare)
    yellow: AgentBandShare = Field(default_factory=AgentBandShare)
    green: AgentBandShare = Field(default_factory=AgentBandShare)


class AgentAggregateStats(OrmBaseModel):
    """`GET /api/v1/agent-scans/aggregate-stats` — the corpus risk meter feed."""

    corpus_count: int = Field(default=0, ge=0)
    gate_target: int = Field(default=500, ge=1)
    gate_met: bool = False
    # Null until the corpus reaches the gate — the frontend blanks the stat to "—".
    pct_with_critical: float | None = None
    band_distribution: AgentBandDistribution = Field(default_factory=AgentBandDistribution)
    window_label: str = "Whole corpus · Last 3 months"


class AgentReplyRequest(OrmBaseModel):
    """`POST /api/v1/agent-scans/r/{token}/reply` — the ≤500-char public reply."""

    text: str = Field(..., min_length=1, max_length=500)
