"""IndexNow submitter.

IndexNow notifies Bing / Yandex / DuckDuckGo / Seznam / Naver / Yep (NOT Google —
Google does not consume it; its value is the Bing→ChatGPT surface) that a URL
changed. A single POST shares the URL set across all participating engines.

The submit is **best-effort + no-op-without-key**: with no `saferskills_indexnow_key`
configured (dev / test / CI) it returns immediately, and any network / HTTP error
is logged and swallowed — it must never break the scan-completion caller.

Outbound host `api.indexnow.org` is a fixed, non-user-controlled, server-initiated
target — outside the SSRF allowlist concern (see `.claude/rules/security.md`
§ Public-input handling #2).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import httpx
import structlog

from app.core.config import get_settings
from app.scan.constants import FEED_EXCLUDED_SOURCES

if TYPE_CHECKING:
    from app.models.catalog_item import CatalogItem
    from app.models.scan import Scan
    from app.models.scan_run import ScanRun

logger = structlog.get_logger(__name__)

INDEXNOW_ENDPOINT = "https://api.indexnow.org/indexnow"
# IndexNow accepts up to 10,000 URLs per request; we send 1-2 per event.
_MAX_URLS = 10_000


async def submit_urls(urls: list[str]) -> None:
    """POST the URL set to IndexNow. No-op without a configured key; never raises."""
    settings = get_settings()
    key = settings.saferskills_indexnow_key
    if not key or not urls:
        return

    body: dict[str, object] = {
        "host": settings.saferskills_site_origin.rstrip("/").split("://")[-1],
        "key": key,
        "urlList": urls[:_MAX_URLS],
    }
    if settings.saferskills_indexnow_key_location:
        body["keyLocation"] = settings.saferskills_indexnow_key_location

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(INDEXNOW_ENDPOINT, json=body)
        # 200/202 accepted; 4xx = key/host problem; 429 = throttle. Log, never raise.
        if resp.status_code >= 400:
            logger.warning(
                "indexnow.rejected",
                status=resp.status_code,
                count=len(body["urlList"]),  # type: ignore[arg-type]
            )
        else:
            logger.debug("indexnow.submitted", status=resp.status_code, count=len(urls))
    except Exception:
        logger.warning("indexnow.failed", count=len(urls))


def indexnow_urls_for_run(run: ScanRun, slugs: list[str]) -> list[str]:
    """Build the IndexNow URL set for a completed scan run, or `[]` if it should
    not be pinged.

    Pings ONLY public, completed, non-firehose runs (D-07-04): the bulk
    `ingestion` / `rescan_rules` sources are in `FEED_EXCLUDED_SOURCES`, so this
    returns `[]` for them — a guaranteed no-op even if a caller hooks them.
    """
    if (
        run.visibility != "public"
        or run.status != "completed"
        or run.source in FEED_EXCLUDED_SOURCES
    ):
        return []

    origin = get_settings().saferskills_site_origin.rstrip("/")
    urls = [f"{origin}/scans/{run.id}"]
    urls += [f"{origin}/items/{slug}" for slug in slugs]
    return urls


def indexnow_urls_for_scan(scan: Scan, item: CatalogItem | None) -> list[str]:
    """Build the IndexNow URL set for a single-capability scan completion
    (the vendor-appeal / legacy `scan_run` path), or `[]` if it should not ping.

    Pings ONLY a public, non-archived item whose scan is completed
    (`tier != 'unscoped'`) and non-firehose (D-07-04). There is no public
    `/scans/<scan_id>` page for a single capability scan (the public report is
    run-keyed), so only the item page URL is emitted.
    """
    if item is None or item.visibility != "public" or item.archived:
        return []
    if scan.tier == "unscoped" or scan.source in FEED_EXCLUDED_SOURCES:
        return []
    origin = get_settings().saferskills_site_origin.rstrip("/")
    return [f"{origin}/items/{item.slug}"]
