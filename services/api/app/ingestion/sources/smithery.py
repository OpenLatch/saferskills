"""Smithery.ai MCP-server aggregator adapter.

Feed-first: paginates the public registry JSON API
`registry.smithery.ai/servers?page=N&pageSize=M` (no auth). The list records carry
displayName + description + a `homepage` that is sometimes a GitHub URL (the OSS
subset) — those get real repo facts via `enrich_repo_facts`; remote/closed servers
have no GitHub coordinate and fall to the fuzzy queue.

HTML fallback: if the JSON feed is unreachable, `_fetch_html` pulls the listing page
(curl_cffi) and yields nothing structured (the SPA is JS-rendered) — the feed is the
real path; the fallback only keeps the cycle from hard-failing.

Cadence: daily 03:15 UTC (staggered against glama 03:30).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

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


@register_adapter("smithery")
class SmitheryAdapter(ScrapingAdapter):
    """Paginate the Smithery registry JSON feed; fall back to HTML on feed failure."""

    def __init__(self, config: SourceConfig) -> None:
        super().__init__(config)

    async def list_items(self, client: Any) -> AsyncIterator[RawItem]:
        feed_base: str = self.config.discovery.get(
            "feed_url", "https://registry.smithery.ai/servers"
        )
        page_size = int(self.config.discovery.get("page_size", 100))
        max_pages = int(self.config.discovery.get("max_pages", 50))

        page = 1
        first_page = await self._fetch_feed(client, f"{feed_base}?page=1&pageSize={page_size}")
        if first_page is None:
            # Feed unreachable → HTML fallback so the cycle records *something*.
            listing_url: str = self.config.discovery.get("listing_url", "https://smithery.ai/")
            try:
                yield await self._fetch_html(listing_url, discovery_path="html")
            except AdapterBlockedError, RobotsTxtDisallow:
                raise
            return

        data = first_page
        while True:
            servers: list[dict[str, Any]] = data.get("servers") or []
            for record in servers:
                qualified = str(record.get("qualifiedName") or "")
                if not qualified:
                    continue
                yield self.raw_from_record(
                    record,
                    source_id=f"smithery/{qualified}",
                    discovery_path="feed",
                    source_rank=record.get("useCount"),
                )
            pagination: dict[str, Any] = data.get("pagination") or {}
            total_pages = int(pagination.get("totalPages") or 1)
            page += 1
            if page > total_pages or page > max_pages:
                break
            nxt = await self._fetch_feed(client, f"{feed_base}?page={page}&pageSize={page_size}")
            if nxt is None:
                break
            data = nxt

    def normalize(self, raw: RawItem) -> NormalizedItem | None:
        if raw.http_status != 200:
            return None
        record: dict[str, Any] = raw.payload_hint
        if not isinstance(record, dict):  # pyright: ignore[reportUnnecessaryIsInstance]
            return None
        qualified = str(record.get("qualifiedName") or "")
        if not qualified:
            return None

        # The `homepage` is occasionally a GitHub URL (OSS servers); parse coords.
        homepage = str(record.get("homepage") or "")
        github_org, github_repo = parse_github_coords(homepage)
        github_url = (
            f"https://github.com/{github_org}/{github_repo}" if github_org and github_repo else None
        )

        display_name = str(record.get("displayName") or qualified.split("/")[-1] or qualified)
        description = str(record.get("description") or "")[:280]
        created = str(record.get("createdAt") or "") or None

        return NormalizedItem(
            github_org=github_org,
            github_repo=github_repo,
            display_name=display_name,
            description=description,
            github_url=github_url,
            # Backlink credits the Smithery listing page (ToS-respect #4).
            source_url=f"https://smithery.ai/servers/{qualified}",
            kind="mcp_server",
            pushed_at=created,
            metadata_files={},  # populated by enrich()
            aggregator_listings=[self.config.name],
        )

    async def enrich(self, client: Any, normalized: NormalizedItem) -> None:
        """Populate GitHub repo facts + manifests so OSS servers tier properly.
        No-op for repo-less (remote/closed) servers."""
        await enrich_repo_facts(client, normalized)
