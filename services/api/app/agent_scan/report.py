"""Agent-scan report projection (I-5.5, Phase 1).

Builds the wire `AgentScanReport` from an `agent_runs` row reading ONLY scalar
columns — never the `findings`/`evidence`/`telemetry` relationships (an async
lazy-load here would raise MissingGreenlet, and the PUBLIC projection must never
touch `agent_evidence`, Codex#7). Phase 1 has no grading, so `findings`/`checks`/
`componentScores` are always empty; Phase 2 hydrates them from `agent_findings`
(+ the private transcript on the token route only).
"""

from __future__ import annotations

from app.core.config import Settings
from app.models.generated.agent_run import AgentRun
from app.schemas.agent_scan import AgentScanReportDetail


def _public_report_url(settings: Settings, run: AgentRun) -> str:
    return f"{settings.public_base_url.rstrip('/')}/agent-scans/{run.id}"


def _share_url(settings: Settings, token: str | None) -> str | None:
    if token is None:
        return None
    return f"{settings.public_base_url.rstrip('/')}/agent-scans/r/{token}"


def build_agent_report(
    run: AgentRun, *, settings: Settings, private: bool
) -> AgentScanReportDetail:
    """Project an `agent_runs` row to the wire report.

    `private=True` (unlisted token route) populates `share_url` + points
    `report_url` at the capability URL; `private=False` (public route) omits the
    share token entirely. Scalar-only — reads NO `findings`/`evidence`/`telemetry`
    relationship (an async lazy-load would raise MissingGreenlet; the public
    projection must never touch `agent_evidence`, Codex#7).
    """
    share_url = _share_url(settings, run.share_token) if private else None
    report_url = (
        share_url if (private and share_url is not None) else _public_report_url(settings, run)
    )

    # model_validate(dict) so Pydantic validates the ORM `str` columns against the
    # DTO's closed Literals at runtime (a static ctor call would mismatch str↔Literal).
    return AgentScanReportDetail.model_validate(
        {
            "id": str(run.id),
            "status": run.status,
            "agent_name": run.agent_name,
            "runtime": run.runtime,
            "score": run.score,
            "band": run.band,
            "verdict_label": run.verdict_label,
            "cap_callout": run.cap_callout,
            "confidence": run.confidence,
            "score_breakdown": run.score_breakdown,
            "trust_labels": run.trust_labels or [],
            "pack_id": run.pack_id,
            "pack_version": run.pack_version,
            "pack_signature_verified": run.pack_signature_verified,
            "capabilities_present": run.capabilities_present or [],
            "capabilities_absent": run.capabilities_absent or [],
            "family_tally": run.family_tally or {},
            "checks": [],
            "findings": [],
            "component_scores": [],
            "visibility": run.visibility,
            "expires_at": run.expires_at,
            "share_url": share_url,
            "report_url": report_url,
            "rubric_version": run.rubric_version,
            "engine_version": run.engine_version,
            "latency_ms": run.latency_ms,
            "scanned_at": run.scanned_at,
        }
    )
