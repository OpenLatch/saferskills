"""Glama.ai MCP-server aggregator adapter.

Feed-first: paginates the public REST API
`glama.ai/api/mcp/v1/servers?first=N&after=<cursor>` (Relay-style cursor, no auth).
Glama records carry `repository.url` (a real GitHub coordinate for most servers), so
`enrich_repo_facts` populates stars/manifests and items tier to medium/high — the
catalog-growth driver of this PR.

HTML fallback: if the JSON feed is unreachable, `_fetch_html` pulls the listing page
to keep the cycle from hard-failing (the feed is the real path).

Cadence: daily 03:30 UTC (staggered against smithery 03:15).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, cast

import structlog

from app.ingestion.config.loader import SourceConfig
from app.ingestion.framework.base_adapter import (
    NormalizedItem,
    RawItem,
    register_adapter,
)
from app.ingestion.framework.exceptions import AdapterBlockedError, RobotsTxtDisallow
from app.ingestion.framework.github_enrich import enrich_repo_facts, parse_github_coords
from app.ingestion.framework.scraping_adapter import ScrapingAdapter

logger = structlog.get_logger(__name__)


def _spdx_from_license(record: dict[str, Any]) -> str | None:
    """Best-effort SPDX id from Glama's `spdxLicense` object (`.../MIT.json` → MIT)."""
    lic_raw = record.get("spdxLicense")
    if not isinstance(lic_raw, dict):
        return None
    lic = cast("dict[str, Any]", lic_raw)
    url = str(lic.get("url") or "")
    if url:
        tail = url.rstrip("/").rsplit("/", 1)[-1]
        spdx = tail.removesuffix(".json")
        if spdx and spdx != "NOASSERTION":
            return spdx
    return None


@register_adapter("glama")
class GlamaAdapter(ScrapingAdapter):
    """Paginate the Glama MCP REST feed; fall back to HTML on feed failure."""

    def __init__(self, config: SourceConfig) -> None:
        super().__init__(config)

    async def list_items(self, client: Any) -> AsyncIterator[RawItem]:
        feed_base: str = self.config.discovery.get(
            "feed_url", "https://glama.ai/api/mcp/v1/servers"
        )
        page_size = int(self.config.discovery.get("page_size", 100))
        max_pages = int(self.config.discovery.get("max_pages", 100))

        after: str | None = None
        pages = 0
        while pages < max_pages:
            url = f"{feed_base}?first={page_size}"
            if after:
                url += f"&after={after}"
            data = await self._fetch_feed(client, url)
            if data is None:
                if pages == 0:
                    # Feed unreachable on the very first page → HTML fallback.
                    listing_url: str = self.config.discovery.get(
                        "listing_url", "https://glama.ai/mcp/servers"
                    )
                    try:
                        yield await self._fetch_html(listing_url, discovery_path="html")
                    except AdapterBlockedError, RobotsTxtDisallow:
                        raise
                return

            servers: list[dict[str, Any]] = data.get("servers") or []
            for record in servers:
                sid = str(record.get("id") or "")
                if not sid:
                    continue
                yield self.raw_from_record(
                    record,
                    source_id=f"glama/{sid}",
                    discovery_path="feed",
                )

            page_info: dict[str, Any] = data.get("pageInfo") or {}
            if not page_info.get("hasNextPage"):
                break
            after = page_info.get("endCursor")
            if not after:
                break
            pages += 1

    def normalize(self, raw: RawItem) -> NormalizedItem | None:
        if raw.http_status != 200:
            return None
        record: dict[str, Any] = raw.payload_hint
        if not isinstance(record, dict):  # pyright: ignore[reportUnnecessaryIsInstance]
            return None
        sid = str(record.get("id") or "")
        if not sid:
            return None

        repo_raw = record.get("repository")
        repo_obj = cast("dict[str, Any]", repo_raw) if isinstance(repo_raw, dict) else {}
        repo_url = str(repo_obj.get("url") or "")
        github_org, github_repo = parse_github_coords(repo_url)
        github_url = (
            f"https://github.com/{github_org}/{github_repo}" if github_org and github_repo else None
        )

        display_name = str(record.get("name") or record.get("namespace") or sid)
        description = str(record.get("description") or "")[:280]

        return NormalizedItem(
            github_org=github_org,
            github_repo=github_repo,
            display_name=display_name,
            description=description,
            license_spdx=_spdx_from_license(record),
            github_url=github_url,
            # Backlink credits the Glama listing page (ToS-respect #4).
            source_url=str(record.get("url") or "") or f"https://glama.ai/mcp/servers/{sid}",
            kind="mcp_server",
            metadata_files={},  # populated by enrich()
            aggregator_listings=[self.config.name],
        )

    async def enrich(self, client: Any, normalized: NormalizedItem) -> None:
        """Populate GitHub repo facts + manifests (Glama records usually have a repo)."""
        await enrich_repo_facts(client, normalized)
