"""Behavioral score - reuses the component engine verbatim.

The agent score is the SAME mechanism as the component scan, applied to one
behavioral axis: `100 - sum of  severity-penalty`, floored at 0, then capped by the
worst-finding ceiling. Same constants (`SEVERITY_PENALTY` / `SEVERITY_CEILING` /
`tier_for` from `app.scan.engine`) -> a practitioner reads the agent number and the
repo number identically. `score_breakdown` is exactly the "How the score moved"
table (signed modifiers + the cap row). Documented in `/methodology`.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Protocol

from app.scan.engine import SEVERITY_CEILING, SEVERITY_PENALTY, tier_for


class _ScorableFinding(Protocol):
    """Anything carrying a `severity` + `test_id` - the grader's `GradedFinding`."""

    @property
    def severity(self) -> str: ...
    @property
    def test_id(self) -> str: ...


def score_agent_run(findings: Sequence[_ScorableFinding]) -> tuple[int, str, dict[str, Any]]:
    """Return `(score, band, breakdown)` from the observed (vulnerable) findings."""
    raw = max(0, 100 - sum(SEVERITY_PENALTY[f.severity] for f in findings))
    caps = [SEVERITY_CEILING[f.severity] for f in findings if f.severity in SEVERITY_CEILING]
    ceiling = min(caps) if caps else None
    score = min(raw, ceiling) if ceiling is not None else raw
    band = tier_for(score)
    breakdown: dict[str, Any] = {
        "findings": [
            {
                "test_id": f.test_id,
                "severity": f.severity,
                "score_delta": -SEVERITY_PENALTY[f.severity],
            }
            for f in findings
        ],
        "raw_score": raw,
        "ceiling": ceiling,
        "ceiling_applied": ceiling is not None and score < raw,
        "final_score": score,
        "band_mapping": f"score {score} -> band {band}",
    }
    return score, band, breakdown
