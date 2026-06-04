"""Pure presentation helpers for the dashboard (rel-time, colour map).

Kept I/O-free so they unit-test without a running Textual app.
"""

from __future__ import annotations

import datetime as dt

# Derived-health-status → Rich colour. healthy=green, running=cyan,
# overdue=yellow, failing/blocked=red, paused=dim, disabled=grey, never_run=blue.
STATUS_STYLE: dict[str, str] = {
    "healthy": "green",
    "running": "cyan",
    "overdue": "yellow",
    "failing": "red",
    "blocked": "red",
    "paused": "grey50",
    "disabled": "grey37",
    "never_run": "blue",
}


def status_style(status: str) -> str:
    return STATUS_STYLE.get(status, "white")


# Overall-rollup chip colour (summary.overall).
OVERALL_STYLE: dict[str, str] = {"healthy": "green", "degraded": "yellow", "critical": "red"}

# Per-run row colour (ingestion_runs.status).
RUN_STATUS_STYLE: dict[str, str] = {"succeeded": "green", "failed": "red", "running": "cyan"}


def overall_style(overall: str) -> str:
    return OVERALL_STYLE.get(overall, "white")


def run_status_style(status: str) -> str:
    return RUN_STATUS_STYLE.get(status, "white")


def status_markup(status: str) -> str:
    """Status name wrapped in its colour for a Rich-markup cell."""
    return f"[{status_style(status)}]{status}[/]"


def _parse(iso: str | None) -> dt.datetime | None:
    if not iso:
        return None
    try:
        return dt.datetime.fromisoformat(iso)
    except ValueError:
        return None


def rel_time(iso: str | None, *, now: dt.datetime | None = None) -> str:
    """Compact relative time: '3m ago', 'in 12m', 'just now', '—' when absent."""
    when = _parse(iso)
    if when is None:
        return "—"
    ref = now or dt.datetime.now(tz=dt.UTC)
    if when.tzinfo is None:
        when = when.replace(tzinfo=dt.UTC)
    delta = (ref - when).total_seconds()
    future = delta < 0
    secs = abs(delta)
    if secs < 45:
        return "just now"
    if secs < 3600:
        val = f"{int(secs // 60)}m"
    elif secs < 86400:
        val = f"{int(secs // 3600)}h"
    else:
        val = f"{int(secs // 86400)}d"
    return f"in {val}" if future else f"{val} ago"


def duration(ms: int | None) -> str:
    if ms is None:
        return "—"
    if ms < 1000:
        return f"{ms}ms"
    return f"{ms / 1000:.1f}s"
