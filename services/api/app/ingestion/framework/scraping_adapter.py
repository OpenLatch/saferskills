"""ScrapingAdapter — Phase B stub.

The 3-tier scrape stack (curl_cffi → Trafilatura → Playwright stealth, D-04-07),
robots.txt enforcement (Protego), and the feed/sitemap-first discovery (D-04-36)
land in Phase B. Declared here in Phase A so Phase B is a pure addition (no churn
to the framework contract) and the worker's `ingest_aggregator` queue exists.
"""

from __future__ import annotations

from app.ingestion.framework.registry_adapter import RegistryAdapter


class ScrapingAdapter(RegistryAdapter):
    """Marker base for scraped-aggregator adapters (Phase B). Inherits the
    registry run-cycle; Phase B overrides the HTTP tier strategy + robots check."""
