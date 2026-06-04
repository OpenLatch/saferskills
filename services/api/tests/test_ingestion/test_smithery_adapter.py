"""Tests for the Smithery aggregator adapter (sources/smithery.py). No live requests."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.ingestion.config.loader import SourceConfig
from app.ingestion.framework.base_adapter import RawItem
from app.ingestion.sources.smithery import SmitheryAdapter

_FEED_RECORD = {
    "id": "abc",
    "qualifiedName": "upstash/context7-mcp",
    "displayName": "Context7",
    "description": "Up-to-date docs for any prompt.",
    "homepage": "https://github.com/upstash/context7#readme",
    "useCount": 999,
    "createdAt": "2025-11-26T14:34:03.393Z",
}
_REMOTE_RECORD = {
    "id": "def",
    "qualifiedName": "gmail",
    "displayName": "Gmail",
    "description": "Manage Gmail.",
    "homepage": "https://smithery.ai/servers/gmail",
    "useCount": 34546,
}


def _config() -> SourceConfig:
    return SourceConfig(
        name="smithery",
        kind="scrape",
        hosts=[
            "registry.smithery.ai",
            "smithery.ai",
            "api.github.com",
            "raw.githubusercontent.com",
        ],
        rate_limit_per_second=50.0,
        queue="ingest_aggregator",
        discovery={"feed_url": "https://registry.smithery.ai/servers"},
    )


def _feed_response(
    records: list[dict[str, Any]], *, total_pages: int = 1, status: int = 200
) -> MagicMock:
    data = {
        "servers": records,
        "pagination": {
            "currentPage": 1,
            "pageSize": 100,
            "totalPages": total_pages,
            "totalCount": len(records),
        },
    }
    r = MagicMock()
    r.status_code = status
    r.json = lambda: data
    r.content = json.dumps(data).encode()
    return r


@pytest.mark.asyncio
async def test_list_items_feed_happy_path() -> None:
    adapter = SmitheryAdapter(_config())
    client = AsyncMock()
    client.get = AsyncMock(return_value=_feed_response([_FEED_RECORD, _REMOTE_RECORD]))

    items = [it async for it in adapter.list_items(client)]
    assert len(items) == 2
    assert all(it.payload_hint["discovery_path"] == "feed" for it in items)
    assert items[0].source_id == "smithery/upstash/context7-mcp"
    assert items[0].payload_hint["source_rank"] == 999


@pytest.mark.asyncio
async def test_list_items_skips_records_without_qualified_name() -> None:
    adapter = SmitheryAdapter(_config())
    client = AsyncMock()
    client.get = AsyncMock(return_value=_feed_response([{"displayName": "no-name"}, _FEED_RECORD]))
    items = [it async for it in adapter.list_items(client)]
    assert len(items) == 1


@pytest.mark.asyncio
async def test_list_items_html_fallback_on_feed_failure() -> None:
    adapter = SmitheryAdapter(_config())
    client = AsyncMock()
    client.get = AsyncMock(return_value=_feed_response([], status=404))  # feed → None

    fallback = RawItem(
        source_id="https://smithery.ai/",
        raw_body_bytes=b"<html></html>",
        raw_body_hash="x",
        http_status=200,
        fetch_tier=1,
        payload_hint={"discovery_path": "html", "url": "https://smithery.ai/"},
    )
    with patch.object(adapter, "_fetch_html", AsyncMock(return_value=fallback)):
        items = [it async for it in adapter.list_items(client)]
    assert len(items) == 1
    assert items[0].payload_hint["discovery_path"] == "html"


def test_normalize_oss_record_extracts_github() -> None:
    adapter = SmitheryAdapter(_config())
    raw = adapter.raw_from_record(
        _FEED_RECORD, source_id="smithery/x", discovery_path="feed", source_rank=999
    )
    n = adapter.normalize(raw)
    assert n is not None
    assert n.github_org == "upstash"
    assert n.github_repo == "context7"
    assert n.github_url == "https://github.com/upstash/context7"
    assert n.kind == "mcp_server"
    assert n.source_url == "https://smithery.ai/servers/upstash/context7-mcp"
    assert n.aggregator_listings == ["smithery"]


def test_normalize_remote_record_has_no_github() -> None:
    adapter = SmitheryAdapter(_config())
    raw = adapter.raw_from_record(_REMOTE_RECORD, source_id="smithery/gmail", discovery_path="feed")
    n = adapter.normalize(raw)
    assert n is not None
    assert n.github_org is None
    assert n.github_url is None
    assert n.display_name == "Gmail"


def test_normalize_returns_none_for_html_fallback_item() -> None:
    adapter = SmitheryAdapter(_config())
    html_raw = RawItem(
        source_id="https://smithery.ai/",
        raw_body_bytes=b"<html></html>",
        raw_body_hash="x",
        http_status=200,
        payload_hint={"discovery_path": "html", "html": "<html></html>"},
    )
    assert adapter.normalize(html_raw) is None


def test_normalize_returns_none_for_error_item() -> None:
    adapter = SmitheryAdapter(_config())
    err = RawItem(source_id="x", raw_body_bytes=b"", raw_body_hash="x", http_status=500)
    assert adapter.normalize(err) is None
