"""Unit tests for the pure ingestion-health state machine (no I/O)."""

from __future__ import annotations

import datetime as dt
from typing import Any

from app.ingestion.framework import health

NOW = dt.datetime(2026, 6, 4, 12, 0, 0, tzinfo=dt.UTC)
# Hourly cadence → 3600s; grace = min(3600, 600) = 600; overdue > 4200s; stale > 7200s.
HOURLY = "0 * * * *"


def _snap(**over: Any) -> health.SourceSnapshot:
    base: dict[str, Any] = {
        "source": "npm",
        "enabled": True,
        "cursor_status": "active",
        "consecutive_failures": 0,
        "last_success_at": NOW - dt.timedelta(minutes=5),
        "last_attempt_at": NOW - dt.timedelta(minutes=5),
        "cadence_cron": HOURLY,
        "has_live_job": False,
        "has_dead_letter": False,
        "running_since": None,
        "runs_total_1h": 2,
        "runs_failed_1h": 0,
        "runs_total_24h": 20,
        "runs_failed_24h": 0,
        "now": NOW,
    }
    base.update(over)
    return health.SourceSnapshot(**base)


# ── derive_status: each of the 8 states ──


def test_status_disabled_by_cursor() -> None:
    assert health.derive_status(_snap(cursor_status="disabled")) == "disabled"


def test_status_disabled_by_config() -> None:
    assert health.derive_status(_snap(enabled=False)) == "disabled"


def test_status_blocked() -> None:
    assert health.derive_status(_snap(cursor_status="blocked")) == "blocked"


def test_status_paused() -> None:
    assert health.derive_status(_snap(cursor_status="paused")) == "paused"


def test_status_running_live_job() -> None:
    assert health.derive_status(_snap(has_live_job=True)) == "running"


def test_status_running_row() -> None:
    assert health.derive_status(_snap(running_since=NOW - dt.timedelta(minutes=2))) == "running"


def test_status_never_run() -> None:
    assert health.derive_status(_snap(last_success_at=None, last_attempt_at=None)) == "never_run"


def test_status_failing_dead_letter() -> None:
    assert health.derive_status(_snap(has_dead_letter=True)) == "failing"


def test_status_failing_consecutive() -> None:
    assert health.derive_status(_snap(consecutive_failures=5)) == "failing"


def test_status_failing_rate() -> None:
    assert health.derive_status(_snap(runs_total_1h=4, runs_failed_1h=3)) == "failing"


def test_status_failing_stale() -> None:
    stale = _snap(
        last_success_at=NOW - dt.timedelta(hours=3),
        last_attempt_at=NOW - dt.timedelta(hours=3),
    )
    assert health.derive_status(stale) == "failing"


def test_status_overdue() -> None:
    od = _snap(
        last_success_at=NOW - dt.timedelta(minutes=75),
        last_attempt_at=NOW - dt.timedelta(minutes=75),
    )
    assert health.derive_status(od) == "overdue"


def test_status_healthy() -> None:
    assert health.derive_status(_snap()) == "healthy"


def test_webhook_source_never_overdue() -> None:
    # cadence_cron None (webhook) → no idle-based overdue/stale.
    s = _snap(cadence_cron=None, last_success_at=NOW - dt.timedelta(days=30))
    assert health.derive_status(s) == "healthy"


# ── classify_critical: each reason_code + tier ──


def test_critical_blocked() -> None:
    sig = health.classify_critical(_snap(cursor_status="blocked"))
    assert sig is not None and sig.reason_code == "blocked" and sig.tier == "critical"


def test_critical_dead_letter() -> None:
    sig = health.classify_critical(_snap(has_dead_letter=True))
    assert sig is not None and sig.reason_code == "dead_letter" and sig.tier == "critical"


def test_critical_stuck() -> None:
    sig = health.classify_critical(
        _snap(running_since=NOW - dt.timedelta(minutes=40), has_live_job=False)
    )
    assert sig is not None and sig.reason_code == "stuck" and sig.tier == "critical"


def test_stuck_false_when_live_job_present() -> None:
    assert not health.is_stuck(
        _snap(running_since=NOW - dt.timedelta(minutes=40), has_live_job=True)
    )


def test_critical_stale() -> None:
    sig = health.classify_critical(_snap(last_success_at=NOW - dt.timedelta(hours=3)))
    assert sig is not None and sig.reason_code == "stale" and sig.tier == "critical"


def test_critical_failure_rate() -> None:
    sig = health.classify_critical(_snap(runs_total_1h=2, runs_failed_1h=2))
    assert sig is not None and sig.reason_code == "failure_rate" and sig.tier == "critical"


def test_critical_consecutive_failures() -> None:
    # No rate signal (empty 1h window) but a high consecutive streak.
    sig = health.classify_critical(_snap(runs_total_1h=0, consecutive_failures=6))
    assert sig is not None and sig.reason_code == "consecutive_failures" and sig.tier == "critical"


def test_warn_paused() -> None:
    sig = health.classify_critical(_snap(cursor_status="paused", runs_total_1h=0))
    assert sig is not None and sig.reason_code == "paused" and sig.tier == "warn"


def test_warn_overdue() -> None:
    sig = health.classify_critical(
        _snap(last_success_at=NOW - dt.timedelta(minutes=75), runs_total_1h=0)
    )
    assert sig is not None and sig.reason_code == "overdue" and sig.tier == "warn"


def test_warn_failure_rate() -> None:
    sig = health.classify_critical(_snap(runs_total_1h=10, runs_failed_1h=1))
    assert sig is not None and sig.reason_code == "failure_rate_warn" and sig.tier == "warn"


def test_clear_returns_none() -> None:
    assert health.classify_critical(_snap()) is None


# ── rollup_overall ──


def test_rollup_critical_wins() -> None:
    sigs = [
        health.CriticalSignal("a", "paused", "warn", ""),
        health.CriticalSignal("b", "stale", "critical", ""),
    ]
    assert health.rollup_overall(sigs) == "critical"


def test_rollup_degraded() -> None:
    sigs = [health.CriticalSignal("a", "paused", "warn", "")]
    assert health.rollup_overall(sigs) == "degraded"


def test_rollup_healthy_when_empty() -> None:
    assert health.rollup_overall([]) == "healthy"


# ── next_expected_run ──


def test_next_expected_run_hourly() -> None:
    nxt = health.next_expected_run(HOURLY, NOW)
    assert nxt == dt.datetime(2026, 6, 4, 13, 0, 0, tzinfo=dt.UTC)


def test_next_expected_run_webhook_none() -> None:
    assert health.next_expected_run(None, NOW) is None
