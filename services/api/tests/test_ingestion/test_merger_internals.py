"""Tests for merger private helpers that don't touch catalog_items.

These cover the helper functions in merger.py that are pure or touch only
the merge_candidates table via raw SQL — avoiding the ORM column name bug on
catalog_items that blocks the full MergeEngine.upsert tests.
"""

from __future__ import annotations

import datetime as dt

from app.ingestion.framework.merger import (
    _merge_source_array,  # pyright: ignore[reportPrivateUsage]
    _now,  # pyright: ignore[reportPrivateUsage]
    _parse_dt,  # pyright: ignore[reportPrivateUsage]
    _source_entry,  # pyright: ignore[reportPrivateUsage]
)


class TestParsedt:
    def test_iso_z_suffix(self) -> None:
        result = _parse_dt("2025-01-01T00:00:00Z")
        assert result is not None
        assert result.tzinfo is not None
        assert result.year == 2025

    def test_iso_plus_tz(self) -> None:
        result = _parse_dt("2025-06-01T12:00:00+00:00")
        assert result is not None

    def test_none_returns_none(self) -> None:
        assert _parse_dt(None) is None

    def test_empty_returns_none(self) -> None:
        assert _parse_dt("") is None

    def test_invalid_string_returns_none(self) -> None:
        assert _parse_dt("not-a-date") is None


class TestSourceEntry:
    def test_source_entry_has_required_fields(self) -> None:
        entry = _source_entry("github_topics", "https://github.com/acme/skill")
        assert entry["registryId"] == "github_topics"
        assert entry["registryUrl"] == "https://github.com/acme/skill"
        assert "firstIndexedAt" in entry
        assert "lastSeenAt" in entry

    def test_source_entry_none_url_uses_empty_string(self) -> None:
        entry = _source_entry("npm", None)
        assert entry["registryUrl"] == ""

    def test_source_entry_timestamps_are_iso_strings(self) -> None:
        entry = _source_entry("pypi", None)
        dt.datetime.fromisoformat(entry["firstIndexedAt"])  # Should not raise
        dt.datetime.fromisoformat(entry["lastSeenAt"])


class TestMergeSourceArray:
    def test_adds_new_registry_when_absent(self) -> None:
        from typing import Any

        existing: list[Any] = []
        result = _merge_source_array(existing, "npm", "https://npmjs.com/foo")
        assert len(result) == 1
        assert result[0]["registryId"] == "npm"

    def test_updates_last_seen_for_existing_registry(self) -> None:
        existing = [
            {
                "registryId": "npm",
                "registryUrl": "https://npmjs.com/foo",
                "firstIndexedAt": "2024-01-01T00:00:00",
                "lastSeenAt": "2024-01-01T00:00:00",
            }
        ]
        result = _merge_source_array(existing, "npm", "https://npmjs.com/foo")
        assert len(result) == 1  # no new entry
        assert result[0]["lastSeenAt"] != "2024-01-01T00:00:00"  # updated

    def test_none_existing_creates_new_array(self) -> None:
        result = _merge_source_array(None, "pypi", "https://pypi.org/project/mcp/")
        assert len(result) == 1

    def test_fills_missing_registry_url(self) -> None:
        existing = [
            {
                "registryId": "npm",
                "registryUrl": "",
                "firstIndexedAt": "2024-01-01",
                "lastSeenAt": "2024-01-01",
            }
        ]
        result = _merge_source_array(existing, "npm", "https://npmjs.com/pkg")
        assert result[0]["registryUrl"] == "https://npmjs.com/pkg"

    def test_adds_second_source_without_removing_first(self) -> None:
        existing = [
            {
                "registryId": "github_topics",
                "registryUrl": "https://github.com/acme/x",
                "firstIndexedAt": "2024-01-01",
                "lastSeenAt": "2024-01-01",
            }
        ]
        result = _merge_source_array(existing, "npm", "https://npmjs.com/x")
        assert len(result) == 2
        registry_ids = {e["registryId"] for e in result}
        assert registry_ids == {"github_topics", "npm"}


class TestNow:
    def test_now_returns_utc_aware_datetime(self) -> None:
        result = _now()
        assert result.tzinfo is not None
        # Check it's close to UTC now
        diff = abs((dt.datetime.now(tz=dt.UTC) - result).total_seconds())
        assert diff < 1.0
