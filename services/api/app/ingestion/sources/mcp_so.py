"""mcp.so aggregator HTML scraper (I-04 Phase B PR2).

Thin SitemapHtmlAdapter subclass — all per-site configuration (sitemap URL, item-URL
filter, name/github extraction knobs) lives in config/sources/mcp_so.yaml. See
`framework/sitemap_scraper.py` for the shared sitemap -> item-page -> og/github logic.
"""

from __future__ import annotations

from app.ingestion.framework.base_adapter import register_adapter
from app.ingestion.framework.sitemap_scraper import SitemapHtmlAdapter


@register_adapter("mcp_so")
class McpSoAdapter(SitemapHtmlAdapter):
    """Scrapes mcp.so via its sitemap. Config-driven; no per-site code."""
