"""Tests for the ScrapingAdapter base (framework/scraping_adapter.py).

curl_cffi network is mocked at `curl_cffi.requests.AsyncSession`; robots.txt is
mocked at the adapter module boundary. No live requests.

This file deliberately exercises the protected fetch primitives (`_fetch_html`,
`_fetch_feed`, `_fetch_sitemap_urls`) directly — they are the base class's
subclass-facing API — so reportPrivateUsage is disabled file-wide.
"""

# pyright: reportPrivateUsage=false

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.ingestion.config.loader import SourceConfig
from app.ingestion.framework.base_adapter import NormalizedItem, RawItem
from app.ingestion.framework.exceptions import (
    AdapterBlockedError,
    OutboundDenyError,
    RobotsTxtDisallow,
)
from app.ingestion.framework.scraping_adapter import (
    ScrapingAdapter,
    is_cloudflare_challenge,
)


class _Probe(ScrapingAdapter):
    """Minimal concrete ScrapingAdapter for exercising the base fetch primitives."""

    async def list_items(self, client: Any) -> AsyncIterator[RawItem]:
        return
        yield  # pragma: no cover  (makes this an async generator)

    def normalize(self, raw: RawItem) -> NormalizedItem | None:
        return None


def _config(hosts: list[str] | None = None) -> SourceConfig:
    return SourceConfig(
        name="smithery",
        kind="scrape",
        hosts=hosts or ["smithery.ai", "registry.smithery.ai"],
        rate_limit_per_second=50.0,
        discovery={},
    )


def _curl_response(*, status: int, headers: dict[str, str], text: str) -> MagicMock:
    r = MagicMock()
    r.status_code = status
    r.headers = headers
    r.text = text
    r.content = text.encode()
    return r


def _patch_curl(response: MagicMock) -> Any:
    session = MagicMock()
    session.get = AsyncMock(return_value=response)
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=session)
    cm.__aexit__ = AsyncMock(return_value=None)
    return patch("curl_cffi.requests.AsyncSession", MagicMock(return_value=cm))


def _allow_robots() -> Any:
    return patch(
        "app.ingestion.framework.scraping_adapter.robots_is_allowed",
        AsyncMock(return_value=True),
    )


# ---------------------------------------------------------------------------
# is_cloudflare_challenge
# ---------------------------------------------------------------------------


def test_cf_detect_via_mitigated_header() -> None:
    assert is_cloudflare_challenge(403, {"cf-mitigated": "challenge"}, "<html></html>")


def test_cf_detect_via_503_server_and_body_marker() -> None:
    assert is_cloudflare_challenge(
        503, {"server": "cloudflare"}, "<html><title>Just a moment...</title></html>"
    )


def test_cf_detect_via_body_script_signature() -> None:
    assert is_cloudflare_challenge(200, {}, "<script>challenge-platform cf-chl</script>")


def test_cf_not_detected_on_normal_page() -> None:
    assert not is_cloudflare_challenge(200, {"server": "nginx"}, "<html>real content</html>")


# ---------------------------------------------------------------------------
# _fetch_html
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_html_cloudflare_raises_blocked() -> None:
    adapter = _Probe(_config())
    resp = _curl_response(
        status=403, headers={"cf-mitigated": "challenge"}, text="Just a moment..."
    )
    with _allow_robots(), _patch_curl(resp), pytest.raises(AdapterBlockedError, match="cloudflare"):
        await adapter._fetch_html("https://smithery.ai/listing")


@pytest.mark.asyncio
async def test_fetch_html_robots_disallow_raises() -> None:
    adapter = _Probe(_config())
    with (
        patch(
            "app.ingestion.framework.scraping_adapter.robots_is_allowed",
            AsyncMock(return_value=False),
        ),
        pytest.raises(RobotsTxtDisallow),
    ):
        await adapter._fetch_html("https://smithery.ai/listing")


@pytest.mark.asyncio
async def test_fetch_html_offsite_host_denied() -> None:
    adapter = _Probe(_config(hosts=["smithery.ai"]))
    with _allow_robots(), pytest.raises(OutboundDenyError):
        await adapter._fetch_html("https://evil.example.com/x")


@pytest.mark.asyncio
async def test_fetch_html_success_returns_raw_item() -> None:
    adapter = _Probe(_config())
    resp = _curl_response(status=200, headers={"server": "nginx"}, text="<html>ok</html>")
    with _allow_robots(), _patch_curl(resp):
        raw = await adapter._fetch_html(
            "https://smithery.ai/listing", discovery_path="html", source_rank=7
        )
    assert raw.http_status == 200
    assert raw.fetch_tier == 1
    assert raw.payload_hint["discovery_path"] == "html"
    assert raw.payload_hint["source_rank"] == 7
    assert raw.error_reason is None


# ---------------------------------------------------------------------------
# _fetch_feed / _fetch_sitemap_urls / extract_main_content
# ---------------------------------------------------------------------------


def _httpx_response(*, status: int, json_data: Any = None, content: bytes = b"") -> MagicMock:
    r = MagicMock()
    r.status_code = status
    r.json = lambda: json_data
    r.content = content
    return r


@pytest.mark.asyncio
async def test_fetch_feed_returns_json_on_200() -> None:
    adapter = _Probe(_config())
    client = AsyncMock()
    client.get = AsyncMock(return_value=_httpx_response(status=200, json_data={"servers": []}))
    assert await adapter._fetch_feed(client, "https://registry.smithery.ai/servers") == {
        "servers": []
    }


@pytest.mark.asyncio
async def test_fetch_feed_returns_none_on_non_200() -> None:
    adapter = _Probe(_config())
    client = AsyncMock()
    client.get = AsyncMock(return_value=_httpx_response(status=404))
    assert await adapter._fetch_feed(client, "https://registry.smithery.ai/servers") is None


@pytest.mark.asyncio
async def test_fetch_sitemap_urls_parses_locs() -> None:
    adapter = _Probe(_config())
    xml = (
        b'<?xml version="1.0"?>'
        b'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        b"<url><loc>https://smithery.ai/a</loc></url>"
        b"<url><loc>https://smithery.ai/b</loc></url>"
        b"</urlset>"
    )
    client = AsyncMock()
    client.get = AsyncMock(return_value=_httpx_response(status=200, content=xml))
    locs = await adapter._fetch_sitemap_urls(client, "https://smithery.ai/sitemap.xml")
    assert locs == ["https://smithery.ai/a", "https://smithery.ai/b"]


@pytest.mark.asyncio
async def test_fetch_sitemap_urls_empty_on_bad_xml() -> None:
    adapter = _Probe(_config())
    client = AsyncMock()
    client.get = AsyncMock(return_value=_httpx_response(status=200, content=b"not xml <<<"))
    assert await adapter._fetch_sitemap_urls(client, "https://smithery.ai/sitemap.xml") == []


def test_extract_main_content_empty() -> None:
    adapter = _Probe(_config())
    assert adapter.extract_main_content("") == ""


def test_extract_main_content_returns_str() -> None:
    adapter = _Probe(_config())
    html = (
        "<html><body><article><p>"
        + ("A meaningful paragraph. " * 20)
        + "</p></article></body></html>"
    )
    out = adapter.extract_main_content(html)
    assert isinstance(out, str)
