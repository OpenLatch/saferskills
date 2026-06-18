"""clawhub.dev aggregator HTML scraper.

Thin SitemapHtmlAdapter subclass — all per-site configuration (sitemap URL, item-URL
filter, name/github extraction knobs) lives in config/sources/clawhub.yaml. See
`framework/sitemap_scraper.py` for the shared sitemap -> item-page -> og/github logic.
"""

from __future__ import annotations

from app.ingestion.framework.base_adapter import register_adapter
from app.ingestion.framework.sitemap_scraper import SitemapHtmlAdapter


@register_adapter("clawhub")
class ClawhubAdapter(SitemapHtmlAdapter):
    """Scrapes clawhub.dev via its sitemap. Config-driven; no per-site code."""
