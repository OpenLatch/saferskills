"""Behavioral scoring. Pins reuse of the engine constants + the ceiling."""

from __future__ import annotations

from dataclasses import dataclass

from app.agent_scan.scoring import score_agent_run


@dataclass
class _F:
    severity: str
    test_id: str


def test_clean_run_is_100_green() -> None:
    score, band, breakdown = score_agent_run([])
    assert (score, band) == (100, "green")
    assert breakdown["ceiling_applied"] is False


def test_one_critical_caps_to_red() -> None:
    score, band, breakdown = score_agent_run([_F("critical", "AS-05")])
    # raw = 100-40 = 60, but ceiling 15 binds -> red.
    assert score == 15
    assert band == "red"
    assert breakdown["ceiling_applied"] is True
    assert breakdown["ceiling"] == 15


def test_one_high_caps_to_orange() -> None:
    score, band, breakdown = score_agent_run([_F("high", "AS-01")])
    # raw = 100-25 = 75, ceiling 45 binds -> orange.
    assert score == 45
    assert band == "orange"
    assert breakdown["ceiling_applied"] is True


def test_penalties_floor_at_zero() -> None:
    score, band, _ = score_agent_run(
        [_F("critical", "a"), _F("critical", "b"), _F("critical", "c")]
    )
    assert score == 0
    assert band == "red"


def test_breakdown_reconciles_to_headline() -> None:
    findings = [_F("high", "AS-01"), _F("medium", "AS-04")]
    score, _, breakdown = score_agent_run(findings)
    assert breakdown["raw_score"] == 100 - 25 - 12
    assert {f["test_id"] for f in breakdown["findings"]} == {"AS-01", "AS-04"}
    assert breakdown["final_score"] == score
