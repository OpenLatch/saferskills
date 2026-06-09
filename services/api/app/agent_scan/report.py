"""Agent-scan report projection (I-5.5).

Projects an `agent_runs` row (+ its `agent_findings` rows) to the wire report.
Pack prose (`title`/`explanation`/`severityRationale`/`remediation`) is JOINED at
build time from the generated pack source by `testId` - mirrors how
`report_builder.py` inlines rule prose via `rule_prose.lookup` (so a pack-version
bump re-renders prose without a finding backfill).

Route-driven evidence split (prime invariant #3, Codex#7):
- **Public** (`private=False`): the caller passes `evidence=None`; `evidenceExcerpt`
  is `None` on every finding; no transcript anywhere; `redacted-public` label.
- **Private** (`private=True`, unlisted token route only): the caller passes the
  raw `agent_evidence.result_json`; per finding we resolve a redacted transcript
  window with the leaked canary highlighted. NEVER persisted, never a trace field.

`checks` (the proof-of-tests row set) is re-derived from the pack + the stored run
columns (`capabilities_present`) + the vulnerable findings - so the PUBLIC route
renders it WITHOUT ever reading `agent_evidence`.
"""

from __future__ import annotations

import re
from functools import lru_cache
from typing import Any

from app.agent_scan.canary import canary, derive_seed, load_master_key
from app.agent_scan.pack import load_pack_source
from app.core.config import Settings
from app.models.generated.agent_finding import AgentFinding
from app.models.generated.agent_run import AgentRun
from app.schemas.agent_scan import AgentScanReportDetail

_MAX_WINDOW_LINES = 9
_MAX_LINE_CHARS = 200

# Redaction (private transcript only) - the leaked canary (`OL-...`) matches none of
# these, so it survives redaction and stays highlightable.
_REDACT_RES = (
    re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),  # emails
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._\-]+"),  # bearer tokens
    re.compile(
        r"sk-[A-Za-z0-9]{16,}|gh[pousr]_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|"
        r"-----BEGIN [A-Z ]+PRIVATE KEY-----"
    ),  # common secret-key shapes
)


@lru_cache(maxsize=1)
def _pack_tests() -> dict[str, dict[str, Any]]:
    """`{testId: test_def}` from the generated pack source (cached for process life)."""
    tests: list[dict[str, Any]] = load_pack_source()["tests"]
    return {str(t["testId"]): t for t in tests}


def _family_of(test_def: dict[str, Any]) -> str:
    owasp: list[str] = list(test_def.get("owasp") or [])
    family: str = test_def.get("categoryLabel") or (owasp[0] if owasp else "uncategorized")
    return family


def _public_report_url(settings: Settings, run: AgentRun) -> str:
    return f"{settings.public_base_url.rstrip('/')}/agent-scans/{run.id}"


def _share_url(settings: Settings, token: str | None) -> str | None:
    return (
        None if token is None else f"{settings.public_base_url.rstrip('/')}/agent-scans/r/{token}"
    )


def report_urls(run: AgentRun, settings: Settings, *, private: bool) -> tuple[str, str | None]:
    """`(report_url, share_url)` - the lightweight pair the status poll needs."""
    share = _share_url(settings, run.share_token) if private else None
    return (share or _public_report_url(settings, run), share)


def _redact(text: str) -> str:
    out = text
    for pattern in _REDACT_RES:
        out = pattern.sub("[REDACTED]", out)
    return out[:_MAX_LINE_CHARS]


def _remediation_dto(test_def: dict[str, Any]) -> dict[str, Any]:
    rem: dict[str, Any] = test_def.get("remediation") or {}
    return {
        "action": rem.get("action", ""),
        "steps": rem.get("steps"),
        "safer_pattern": rem.get("saferPattern"),
    }


def _private_excerpt(
    evidence: dict[str, Any], finding: AgentFinding, seed: bytes
) -> dict[str, Any] | None:
    """Redacted transcript window for one finding, leaked canary highlighted."""
    test = next((t for t in evidence.get("tests", []) if t.get("test_id") == finding.test_id), None)
    if test is None:
        return None
    canary_val = (
        canary(seed, finding.leaked_canary_slot, finding.test_id)
        if finding.leaked_canary_slot
        else None
    )
    lines: list[dict[str, Any]] = []
    raw_segments: list[str] = []
    for turn in test.get("turns", []):
        if turn.get("role") == "agent":
            raw_segments.extend((turn.get("raw_response") or "").splitlines() or [""])
    for call in test.get("tool_calls", []):
        raw_segments.append(f"{call.get('name', '?')}({call.get('args', {})})")

    truncated = len(raw_segments) > _MAX_WINDOW_LINES
    for idx, raw in enumerate(raw_segments[:_MAX_WINDOW_LINES], start=1):
        hit = canary_val is not None and canary_val in raw
        lines.append({"line_no": idx, "text": _redact(raw), "hit": hit})
    if not lines:
        return None
    return {
        "file": f"transcript:{finding.test_id}",
        "lang": None,
        "truncated": truncated,
        "lines": lines,
    }


def _finding_dto(
    finding: AgentFinding, *, evidence: dict[str, Any] | None, seed: bytes | None
) -> dict[str, Any]:
    test_def = _pack_tests().get(finding.test_id, {})
    excerpt = (
        _private_excerpt(evidence, finding, seed)
        if evidence is not None and seed is not None
        else None
    )
    return {
        "id": str(finding.id),
        "test_id": finding.test_id,
        "severity": finding.severity,
        "verdict": finding.verdict,
        "family": finding.family,
        "owasp_refs": finding.owasp_refs or [],
        "atlas_refs": finding.atlas_refs or [],
        "nist_refs": finding.nist_refs or [],
        "score_delta": finding.score_delta,
        "detection_rule": finding.detection_rule,
        "leaked_canary_slot": finding.leaked_canary_slot,
        "title": test_def.get("title", finding.test_id),
        "explanation": test_def.get("explanation", ""),
        "severity_rationale": test_def.get("severityRationale"),
        "category_label": test_def.get("categoryLabel"),
        "remediation": _remediation_dto(test_def),
        "evidence_excerpt": excerpt,
    }


def _build_checks(run: AgentRun, vulnerable_ids: set[str]) -> list[dict[str, Any]]:
    """Re-derive the proof-of-tests rows from the pack + stored run columns + the
    vulnerable findings - NO evidence read (public-route safe). Empty until graded."""
    if run.status not in ("graded", "published"):
        return []
    caps_present = set(run.capabilities_present or [])
    checks: list[dict[str, Any]] = []
    for test_def in _pack_tests().values():  # cached {testId: test_def}, pack order
        tid: str = test_def["testId"]
        if tid in vulnerable_ids:
            verdict = "vulnerable"
        elif test_def["tier"] != "launch" and test_def["requiredCapability"] not in caps_present:
            verdict = "n_a"
        else:
            verdict = "not_observed"
        checks.append(
            {
                "test_id": tid,
                "family": _family_of(test_def),
                "title": test_def.get("title", tid),
                "verdict": verdict,
                "severity": test_def["severity"],
            }
        )
    return checks


def build_agent_report(
    run: AgentRun,
    findings: list[AgentFinding],
    *,
    settings: Settings,
    private: bool,
    evidence: dict[str, Any] | None = None,
) -> AgentScanReportDetail:
    """Project a run (+ its findings) to the wire report.

    `private=False` (public route) MUST pass `evidence=None` - the public path never
    reads `agent_evidence`. `private=True` (token route) passes the raw
    `result_json`; the transcript window is resolved per finding at request time.
    """
    report_url, share_url = report_urls(run, settings, private=private)
    seed = (
        derive_seed(load_master_key(), str(run.id), run.nonce)
        if private and evidence is not None
        else None
    )
    vulnerable_ids = {f.test_id for f in findings}
    finding_dtos = [
        _finding_dto(f, evidence=evidence if private else None, seed=seed) for f in findings
    ]

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
            "checks": _build_checks(run, vulnerable_ids),
            "findings": finding_dtos,
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
