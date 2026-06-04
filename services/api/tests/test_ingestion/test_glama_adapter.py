"""Tests for the Glama aggregator adapter (sources/glama.py). No live requests."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.ingestion.config.loader import SourceConfig
from app.ingestion.framework.base_adapter import RawItem
from app.ingestion.sources.glama import (
    GlamaAdapter,
    _spdx_from_license,  # pyright: ignore[reportPrivateUsage]
)

_RECORD = {
    "id": "bschbgoc53",
    "name": "AgentTrust MCP Server",
    "namespace": "agenttrust",
    "slug": "mcp-server",
    "url": "https://glama.ai/mcp/servers/bschbgoc53",
    "description": "Email, IM, and cloud file storage for AI agents.",
    "repository": {"url": "https://github.com/agenttrust/mcp-server"},
    "spdxLicense": {"name": "MIT License", "url": "https://spdx.org/licenses/MIT.json"},
}


def _config() -> SourceConfig:
    return SourceConfig(
        name="glama",
        kind="scrape",
        hosts=["glama.ai", "api.github.com", "raw.githubusercontent.com"],
        rate_limit_per_second=50.0,
        queue="ingest_aggregator",
        discovery={"feed_url": "https://glama.ai/api/mcp/v1/servers"},
    )


def _feed_response(
    records: list[dict[str, Any]], *, has_next: bool = False, status: int = 200
) -> MagicMock:
    data = {
        "pageInfo": {"hasNextPage": has_next, "endCursor": "CURSOR2" if has_next else None},
        "servers": records,
    }
    r = MagicMock()
    r.status_code = status
    r.json = lambda: data
    r.content = json.dumps(data).encode()
    return r


def test_spdx_from_license() -> None:
    assert _spdx_from_license(_RECORD) == "MIT"
    assert (
        _spdx_from_license({"spdxLicense": {"url": "https://spdx.org/licenses/NOASSERTION.json"}})
        is None
    )
    assert _spdx_from_license({}) is None


@pytest.mark.asyncio
async def test_list_items_feed_happy_path() -> None:
    adapter = GlamaAdapter(_config())
    client = AsyncMock()
    client.get = AsyncMock(return_value=_feed_response([_RECORD]))
    items = [it async for it in adapter.list_items(client)]
    assert len(items) == 1
    assert items[0].source_id == "glama/bschbgoc53"
    assert items[0].payload_hint["discovery_path"] == "feed"


@pytest.mark.asyncio
async def test_list_items_follows_cursor_pages() -> None:
    adapter = GlamaAdapter(_config())
    rec2 = {**_RECORD, "id": "second"}
    client = AsyncMock()
    client.get = AsyncMock(
        side_effect=[
            _feed_response([_RECORD], has_next=True),
            _feed_response([rec2], has_next=False),
        ]
    )
    items = [it async for it in adapter.list_items(client)]
    assert [it.source_id for it in items] == ["glama/bschbgoc53", "glama/second"]


@pytest.mark.asyncio
async def test_list_items_html_fallback_on_feed_failure() -> None:
    adapter = GlamaAdapter(_config())
    client = AsyncMock()
    client.get = AsyncMock(return_value=_feed_response([], status=500))
    fallback = RawItem(
        source_id="https://glama.ai/mcp/servers",
        raw_body_bytes=b"<html></html>",
        raw_body_hash="x",
        http_status=200,
        payload_hint={"discovery_path": "html", "url": "https://glama.ai/mcp/servers"},
    )
    with patch.object(adapter, "_fetch_html", AsyncMock(return_value=fallback)):
        items = [it async for it in adapter.list_items(client)]
    assert len(items) == 1
    assert items[0].payload_hint["discovery_path"] == "html"


def test_normalize_extracts_github_and_license() -> None:
    adapter = GlamaAdapter(_config())
    raw = adapter.raw_from_record(_RECORD, source_id="glama/x", discovery_path="feed")
    n = adapter.normalize(raw)
    assert n is not None
    assert n.github_org == "agenttrust"
    assert n.github_repo == "mcp-server"
    assert n.github_url == "https://github.com/agenttrust/mcp-server"
    assert n.license_spdx == "MIT"
    assert n.source_url == "https://glama.ai/mcp/servers/bschbgoc53"
    assert n.kind == "mcp_server"
    assert n.aggregator_listings == ["glama"]


def test_normalize_without_repository() -> None:
    adapter = GlamaAdapter(_config())
    rec = {"id": "x", "name": "No Repo Server", "namespace": "noo", "description": "d"}
    raw = adapter.raw_from_record(rec, source_id="glama/x", discovery_path="feed")
    n = adapter.normalize(raw)
    assert n is not None
    assert n.github_org is None
    assert n.github_url is None
    assert n.source_url == "https://glama.ai/mcp/servers/x"


def test_normalize_returns_none_for_error_item() -> None:
    adapter = GlamaAdapter(_config())
    err = RawItem(source_id="x", raw_body_bytes=b"", raw_body_hash="x", http_status=503)
    assert adapter.normalize(err) is None
