"""Process RSS readout — stdlib only, no psutil dependency.

A lightweight resident-set-size probe for memory observability: the worker logs
`memory.rss_mb` at the end of each scan job and ingestion cycle so a creeping
footprint (the OOM-loop signal on a small machine) is visible in structlog
without a metrics pipeline. Reads `/proc/self/status` (Linux — the deploy
target); returns None anywhere it can't (Windows/macOS dev, missing procfs),
so a call site never needs an OS guard.
"""

from __future__ import annotations

from pathlib import Path

_STATUS_PATH = Path("/proc/self/status")


def _parse_vmrss_kb(status_text: str) -> int | None:
    """Extract the `VmRSS:` value (in KiB) from /proc/self/status text.

    Pure + unit-testable. Returns None if the field is absent or malformed.
    Example line: `VmRSS:\t  401234 kB`.
    """
    for line in status_text.splitlines():
        if line.startswith("VmRSS:"):
            parts = line.split()
            # ["VmRSS:", "<number>", "kB"]
            if len(parts) >= 2 and parts[1].isdigit():
                return int(parts[1])
            return None
    return None


def _read_status() -> str | None:
    """Read /proc/self/status, or None when it isn't available (the test seam)."""
    try:
        return _STATUS_PATH.read_text()
    except OSError:
        return None


def rss_mb() -> float | None:
    """Current process resident set size in MiB, or None when unavailable.

    Linux-only (reads /proc/self/status). Any failure — no procfs (Windows /
    macOS), permission, parse error — yields None so callers can log
    unconditionally (`rss_mb=None` is a fine structlog value).
    """
    status = _read_status()
    if status is None:
        return None
    kb = _parse_vmrss_kb(status)
    if kb is None:
        return None
    return round(kb / 1024, 1)
