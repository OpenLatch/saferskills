"""Pure ingestion-health state machine + rollup (eagle-eye view).

No I/O — every function takes a plain `SourceSnapshot` of cheap reads
(crawler_cursors + ingestion_runs aggregates + procrastinate_jobs flags) and
returns a verdict. The thresholds + cadence math are imported from `alerts.py`
so the dashboard and the 15-min `alert_evaluator` agree on what "failing" means
(no duplication).

Three entry points, used by `GET /api/v1/admin/sources`:
  - `derive_status` → the 8-state machine (first-match-wins).
  - `classify_critical` → the single highest-severity signal for one source.
  - `rollup_overall` → worst-condition across all sources.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from croniter import croniter

# Single source of truth for the failure-rate thresholds + cadence math — shared
# with the 15-min alert_evaluator so the dashboard and the pager agree (no
# duplication).
from app.ingestion.framework.alerts import PAGE_1H, PAGE_24H, WARN_1H, cadence_seconds

# A source with this many consecutive cursor failures is treated as critical even
# if the rolling failure-rate window is empty (e.g. it fails before writing a run).
_CONSECUTIVE_FAIL_CRITICAL = 5
# A `running` ingestion_runs row older than this, with no live procrastinate job,
# is a zombie/stuck cycle — surfaced in critical[], auto-reaper is a follow-up.
_STUCK_SECONDS = 1800.0
# Overdue grace on top of one cadence interval, capped so fast cadences don't wait.
_GRACE_CAP_SECONDS = 600.0

VALID_STATUSES = (
    "disabled",
    "blocked",
    "paused",
    "running",
    "never_run",
    "failing",
    "overdue",
    "healthy",
)


@dataclass(frozen=True)
class SourceSnapshot:
    """Cheap, already-read inputs for one source's health verdict."""

    source: str
    enabled: bool
    cursor_status: str  # active | paused | blocked | disabled
    consecutive_failures: int
    last_success_at: dt.datetime | None
    last_attempt_at: dt.datetime | None
    cadence_cron: str | None
    has_live_job: bool  # a procrastinate job in status='doing'
    has_dead_letter: bool  # a procrastinate job in status='failed' (retries exhausted)
    running_since: dt.datetime | None  # oldest running ingestion_runs row, if any
    runs_total_1h: int
    runs_failed_1h: int
    runs_total_24h: int
    runs_failed_24h: int
    now: dt.datetime


@dataclass(frozen=True)
class CriticalSignal:
    source: str
    reason_code: str
    tier: str  # "critical" | "warn"
    detail: str


def failure_rate_1h(s: SourceSnapshot) -> float:
    return s.runs_failed_1h / s.runs_total_1h if s.runs_total_1h else 0.0


def failure_rate_24h(s: SourceSnapshot) -> float:
    return s.runs_failed_24h / s.runs_total_24h if s.runs_total_24h else 0.0


def next_expected_run(cadence_cron: str | None, after: dt.datetime) -> dt.datetime | None:
    """Next cron fire strictly after `after`, or None for a webhook source."""
    if not cadence_cron:
        return None
    try:
        return croniter(cadence_cron, after).get_next(dt.datetime)
    except ValueError, KeyError:
        return None


def _overdue_age(s: SourceSnapshot) -> tuple[float, float] | None:
    """(age_seconds_since_last_success, cadence_seconds) — None when not applicable
    (webhook source, or never a successful cycle)."""
    cadence = cadence_seconds(s.cadence_cron)
    if cadence is None or s.last_success_at is None:
        return None
    age = (s.now - s.last_success_at).total_seconds()
    return age, cadence


def is_overdue(s: SourceSnapshot) -> bool:
    pair = _overdue_age(s)
    if pair is None:
        return False
    age, cadence = pair
    grace = min(cadence, _GRACE_CAP_SECONDS)
    return age > cadence + grace


def is_stale(s: SourceSnapshot) -> bool:
    """No successful cycle in 2x the cadence — the page-tier silence threshold."""
    pair = _overdue_age(s)
    if pair is None:
        return False
    age, cadence = pair
    return age > cadence * 2


def is_stuck(s: SourceSnapshot) -> bool:
    if s.running_since is None or s.has_live_job:
        return False
    return (s.now - s.running_since).total_seconds() > _STUCK_SECONDS


def derive_status(s: SourceSnapshot) -> str:
    """The 8-state machine, first-match-wins."""
    if s.cursor_status == "disabled" or not s.enabled:
        return "disabled"
    if s.cursor_status == "blocked":
        return "blocked"
    if s.cursor_status == "paused":
        return "paused"
    if s.has_live_job or s.running_since is not None:
        return "running"
    if s.last_success_at is None and s.last_attempt_at is None:
        return "never_run"
    if (
        s.has_dead_letter
        or s.consecutive_failures >= _CONSECUTIVE_FAIL_CRITICAL
        or failure_rate_1h(s) > PAGE_1H
        or failure_rate_24h(s) > PAGE_24H
        or is_stale(s)
    ):
        return "failing"
    if is_overdue(s):
        return "overdue"
    return "healthy"


def classify_critical(s: SourceSnapshot) -> CriticalSignal | None:
    """The single highest-severity signal for one source, or None when clear.

    Critical tier (page-worthy): blocked, dead_letter, stuck, stale, failure_rate,
    consecutive_failures. Warn tier: paused, overdue, failure_rate_warn.
    """
    fr_1h = failure_rate_1h(s)
    fr_24h = failure_rate_24h(s)

    # ── critical ──
    if s.cursor_status == "blocked":
        return CriticalSignal(s.source, "blocked", "critical", "source blocked")
    if s.has_dead_letter:
        return CriticalSignal(s.source, "dead_letter", "critical", "retries exhausted")
    if is_stuck(s):
        return CriticalSignal(s.source, "stuck", "critical", "running cycle is stuck (>30m)")
    if is_stale(s):
        return CriticalSignal(s.source, "stale", "critical", "no successful cycle in 2x cadence")
    if fr_1h > PAGE_1H or fr_24h > PAGE_24H:
        return CriticalSignal(
            s.source,
            "failure_rate",
            "critical",
            f"failure rate {fr_1h:.0%}/1h {fr_24h:.0%}/24h",
        )
    if s.consecutive_failures >= _CONSECUTIVE_FAIL_CRITICAL:
        return CriticalSignal(
            s.source,
            "consecutive_failures",
            "critical",
            f"{s.consecutive_failures} consecutive failures",
        )

    # ── warn ──
    if s.cursor_status == "paused":
        return CriticalSignal(s.source, "paused", "warn", "source paused")
    if is_overdue(s):
        return CriticalSignal(s.source, "overdue", "warn", "cycle overdue")
    if fr_1h > WARN_1H:
        return CriticalSignal(s.source, "failure_rate_warn", "warn", f"failure rate {fr_1h:.0%}/1h")

    return None


def rollup_overall(signals: list[CriticalSignal]) -> str:
    """Worst condition across all source signals."""
    if any(sig.tier == "critical" for sig in signals):
        return "critical"
    if any(sig.tier == "warn" for sig in signals):
        return "degraded"
    return "healthy"
