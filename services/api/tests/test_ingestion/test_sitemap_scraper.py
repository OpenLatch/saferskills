"""Tests for the SitemapHtmlAdapter base + the 7 PR2 HTML scrapers. No live requests.

The 7 aggregator adapters (mcp_so, pulsemcp, clawhub, skillsmp, skills_sh,
claudeskills_info, skillhub_club) are config-only subclasses of SitemapHtmlAdapter,
so the base's logic IS their logic — exercised here with inline HTML fixtures + a
mocked `_fetch_html`. A parametrized test then asserts every one of the 7 registers
with a valid, loadable config.

This file deliberately exercises the base's protected helpers (`_extract_github`,
`_item_urls`, …) + module-private parsers (`_locs`, `_is_index`), so
reportPrivateUsage is disabled file-wide.
"""

# pyright: reportPrivateUsage=false

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest

import app.ingestion.sources  # noqa: F401  # pyright: ignore[reportUnusedImport]  — populate ADAPTER_REGISTRY
from app.ingestion.config.loader import SourceConfig, load_source_configs
from app.ingestion.framework.base_adapter import ADAPTER_REGISTRY, RawItem, build_adapter
from app.ingestion.framework.sitemap_scraper import (
    SitemapHtmlAdapter,
    _is_index,
    _locs,
)

_SITEMAP_INDEX = (
    '<?xml version="1.0"?>'
    '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
    "<sitemap><loc>https://ex.com/sitemap_projects_1.xml</loc></sitemap>"
    "<sitemap><loc>https://ex.com/sitemap_tags_1.xml</loc></sitemap>"
    "</sitemapindex>"
)
_CHILD_URLSET = (
    '<?xml version="1.0"?>'
    '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
    "<url><loc>https://ex.com/server/widget/acme</loc></url>"
    "<url><loc>https://ex.com/about</loc></url>"
    "<url><loc>https://ex.com/server/gadget/zorp</loc></url>"
    "</urlset>"
)
_ITEM_HTML = """<html><head>
<meta property="og:title" content="Widget MCP - Free Tool | Example Hub"/>
<meta property="og:description" content="A widget server that does widget things."/>
</head><body>
<a href="https://github.com/modelcontextprotocol/registry">spec</a>
<a href="https://github.com/acme/widget-mcp">source</a>
</body></html>"""


def _cfg(**discovery: Any) -> SourceConfig:
    base = {
        "sitemap_url": "https://ex.com/sitemap.xml",
        "item_url_regex": r"ex\.com/server/[^/]+/[^/]+$",
        "item_sitemap_substr": ["projects"],
    }
    base.update(discovery)
    return SourceConfig(
        name="mcp_so",
        kind="scrape",
        hosts=["ex.com", "api.github.com", "raw.githubusercontent.com"],
        rate_limit_per_second=50.0,
        discovery=base,
    )


def _raw(status: int, html: str, item_url: str = "https://ex.com/server/widget/acme") -> RawItem:
    return RawItem(
        source_id=item_url,
        raw_body_bytes=html.encode(),
        raw_body_hash="x",
        http_status=status,
        fetch_tier=1,
        payload_hint={"html": html, "item_url": item_url, "discovery_path": "sitemap"},
    )


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def test_locs_parses_urlset() -> None:
    assert _locs(_CHILD_URLSET) == [
        "https://ex.com/server/widget/acme",
        "https://ex.com/about",
        "https://ex.com/server/gadget/zorp",
    ]


def test_locs_bad_xml_returns_empty() -> None:
    assert _locs("not xml <<<") == []


def test_is_index() -> None:
    assert _is_index(_SITEMAP_INDEX)
    assert not _is_index(_CHILD_URLSET)


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------


def test_extract_github_skips_global_and_site_denylist() -> None:
    # modelcontextprotocol/registry is globally denylisted → acme/widget-mcp wins.
    adapter = SitemapHtmlAdapter(_cfg())
    assert adapter._extract_github(_ITEM_HTML) == ("acme", "widget-mcp")


def test_extract_github_per_site_denylist() -> None:
    adapter = SitemapHtmlAdapter(_cfg(github_denylist=["acme/widget-mcp"]))
    # both candidates denylisted (registry global + acme/widget-mcp site) → none
    assert adapter._extract_github(_ITEM_HTML) == (None, None)


def test_extract_name_og_title_stripped() -> None:
    from bs4 import BeautifulSoup

    adapter = SitemapHtmlAdapter(_cfg(name_from="og_title", name_strip=[" - Free Tool"]))
    soup = BeautifulSoup(_ITEM_HTML, "lxml")
    # " - Free Tool" stripped, then " | Example Hub" branding split off → "Widget MCP"
    assert adapter._extract_name(soup, "https://ex.com/server/widget/acme") == "Widget MCP"


def test_extract_name_slug_index() -> None:
    from bs4 import BeautifulSoup

    adapter = SitemapHtmlAdapter(_cfg(name_from="slug", name_slug_index=-2))
    soup = BeautifulSoup("<html></html>", "lxml")
    # /server/widget/acme with index -2 → "widget"
    assert adapter._extract_name(soup, "https://ex.com/server/widget/acme") == "widget"


# ---------------------------------------------------------------------------
# normalize
# ---------------------------------------------------------------------------


def test_normalize_extracts_all_fields() -> None:
    adapter = SitemapHtmlAdapter(_cfg(kind="mcp_server", name_strip=[" - Free Tool"]))
    n = adapter.normalize(_raw(200, _ITEM_HTML))
    assert n is not None
    assert n.display_name == "Widget MCP"
    assert n.github_url == "https://github.com/acme/widget-mcp"
    assert n.description == "A widget server that does widget things."
    assert n.kind == "mcp_server"
    assert n.source_url == "https://ex.com/server/widget/acme"
    assert n.aggregator_listings == ["mcp_so"]


def test_normalize_non_200_returns_none() -> None:
    adapter = SitemapHtmlAdapter(_cfg())
    assert adapter.normalize(_raw(404, "")) is None


def test_normalize_empty_html_returns_none() -> None:
    adapter = SitemapHtmlAdapter(_cfg())
    assert adapter.normalize(_raw(200, "")) is None


def test_normalize_no_github_still_indexes() -> None:
    adapter = SitemapHtmlAdapter(_cfg())
    html = '<html><head><meta property="og:title" content="No Repo Skill"/></head></html>'
    n = adapter.normalize(_raw(200, html))
    assert n is not None
    assert n.display_name == "No Repo Skill"
    assert n.github_url is None  # repo-less → fuzzy queue, still indexed


# ---------------------------------------------------------------------------
# list_items / _item_urls (mocked _fetch_html)
# ---------------------------------------------------------------------------


def _fetch_html_router(responses: dict[str, str]) -> Any:
    """Return an async fake of _fetch_html that maps url → html (status 0 if absent)."""

    async def fake(url: str, *, discovery_path: str = "html", source_rank: Any = None) -> RawItem:
        if url in responses:
            return _raw(200, responses[url], item_url=url)
        return RawItem(
            source_id=url,
            raw_body_bytes=b"",
            raw_body_hash="x",
            http_status=0,
            fetch_tier=1,
            payload_hint={"html": "", "discovery_path": discovery_path},
        )

    return fake


@pytest.mark.asyncio
async def test_item_urls_recurses_index_and_filters() -> None:
    adapter = SitemapHtmlAdapter(_cfg())
    responses = {
        "https://ex.com/sitemap.xml": _SITEMAP_INDEX,
        "https://ex.com/sitemap_projects_1.xml": _CHILD_URLSET,
    }
    with patch.object(adapter, "_fetch_html", side_effect=_fetch_html_router(responses)):
        urls = await adapter._item_urls(client=None)
    # /about filtered out by item_url_regex; only the two /server/ items remain.
    assert urls == [
        "https://ex.com/server/widget/acme",
        "https://ex.com/server/gadget/zorp",
    ]


@pytest.mark.asyncio
async def test_item_urls_unreachable_sitemap_returns_empty() -> None:
    adapter = SitemapHtmlAdapter(_cfg())  # no response registered → status 0
    with patch.object(adapter, "_fetch_html", side_effect=_fetch_html_router({})):
        assert await adapter._item_urls(client=None) == []


@pytest.mark.asyncio
async def test_item_urls_respects_max_items() -> None:
    adapter = SitemapHtmlAdapter(_cfg(max_items=1))
    responses = {
        "https://ex.com/sitemap.xml": _SITEMAP_INDEX,
        "https://ex.com/sitemap_projects_1.xml": _CHILD_URLSET,
    }
    with patch.object(adapter, "_fetch_html", side_effect=_fetch_html_router(responses)):
        urls = await adapter._item_urls(client=None)
    assert len(urls) == 1


@pytest.mark.asyncio
async def test_list_items_yields_per_item_with_html() -> None:
    adapter = SitemapHtmlAdapter(_cfg(max_items=2))
    responses = {
        "https://ex.com/sitemap.xml": _SITEMAP_INDEX,
        "https://ex.com/sitemap_projects_1.xml": _CHILD_URLSET,
        "https://ex.com/server/widget/acme": _ITEM_HTML,
        "https://ex.com/server/gadget/zorp": _ITEM_HTML,
    }
    with patch.object(adapter, "_fetch_html", side_effect=_fetch_html_router(responses)):
        items = [it async for it in adapter.list_items(client=None)]
    assert len(items) == 2
    assert all(it.payload_hint.get("item_url") for it in items)
    assert items[0].source_id == "mcp_so/https://ex.com/server/widget/acme"


# ---------------------------------------------------------------------------
# All 7 PR2 adapters: registered + valid config
# ---------------------------------------------------------------------------

_PR2_SOURCES = [
    "mcp_so",
    "pulsemcp",
    "clawhub",
    "skillsmp",
    "skills_sh",
    "claudeskills_info",
    "skillhub_club",
]


@pytest.mark.parametrize("name", _PR2_SOURCES)
def test_pr2_adapter_registered_and_configured(name: str) -> None:
    import re

    assert name in ADAPTER_REGISTRY
    adapter = build_adapter(name)
    assert isinstance(adapter, SitemapHtmlAdapter)
    cfg = load_source_configs()[name]
    assert cfg.enabled and cfg.kind == "scrape" and cfg.cadence_cron
    assert cfg.queue == "ingest_aggregator"
    # github hosts present for the enrich() pass. Use set.issubset over exact host
    # strings — NOT `"host" in cfg.hosts`, which trips CodeQL
    # py/incomplete-url-substring-sanitization (it can't tell cfg.hosts is a
    # list[str] of exact hosts, not a URL); cf. http_client.py's `any(host == …)`.
    assert {"api.github.com", "raw.githubusercontent.com"}.issubset(cfg.hosts)
    # discovery is well-formed: sitemap_url + a compilable item_url_regex
    assert cfg.discovery.get("sitemap_url", "").startswith("https://")
    re.compile(cfg.discovery["item_url_regex"])
