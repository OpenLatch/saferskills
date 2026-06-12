"""Unit tests for the stdlib RSS probe (app/core/memory.py)."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core import memory
from app.core.memory import _parse_vmrss_kb, rss_mb  # pyright: ignore[reportPrivateUsage]

_STATUS_SAMPLE = """\
Name:\tpython
VmPeak:\t  512000 kB
VmRSS:\t  401234 kB
Threads:\t12
"""


def test_parse_vmrss_kb_extracts_value() -> None:
    assert _parse_vmrss_kb(_STATUS_SAMPLE) == 401234


def test_parse_vmrss_kb_absent_field() -> None:
    assert _parse_vmrss_kb("Name:\tpython\nThreads:\t1\n") is None


def test_parse_vmrss_kb_malformed() -> None:
    assert _parse_vmrss_kb("VmRSS:\tnot-a-number kB\n") is None


def test_rss_mb_converts_kb_to_mb(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(memory, "_read_status", lambda: _STATUS_SAMPLE)
    assert rss_mb() == round(401234 / 1024, 1)  # 391.8 MiB


def test_rss_mb_none_when_unreadable(monkeypatch: pytest.MonkeyPatch) -> None:
    """No procfs (Windows/macOS dev) → None, never an exception."""
    monkeypatch.setattr(memory, "_read_status", lambda: None)
    assert rss_mb() is None


def test_rss_mb_none_when_field_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(memory, "_read_status", lambda: "Name:\tx\n")
    assert rss_mb() is None


def test_status_path_is_proc_self_status() -> None:
    assert Path("/proc/self/status") == memory._STATUS_PATH  # pyright: ignore[reportPrivateUsage]
