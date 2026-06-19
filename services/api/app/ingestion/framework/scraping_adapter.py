"""ScrapingAdapter — aggregator HTML/feed scraping base (lean).

Inherits the generic `RegistryAdapter.run_cycle` (list_items → 304-skip → normalize
→ enrich → merge → outbox); subclasses override only `list_items` / `normalize` /
`enrich`. This base adds the scrape-specific fetch primitives:

- **Discovery precedence**: feed (JSON) → sitemap → HTML fallback. The
  tier-0 feed/sitemap fetches go through the inherited HTTPX client (SSRF allowlist
  + Hishel RFC-9111 cache). The tier-1 HTML fetch goes through curl_cffi (browser
  impersonation), which BYPASSES the HTTPX transport — so it calls
  `allowlist.assert_host_allowed` + `scraping_rate_limit.acquire_scrape_slot` +
  `robots.is_allowed` itself before every request.
- **Lean stack — no Playwright.** A Cloudflare interstitial is detected and surfaced
  as `AdapterBlockedError`; the cycle wrapper (`tasks.run_source_cycle`) flips the
  source to `status='blocked'`. There is no tier-3 stealth-browser fallback (dropped
  to keep the Fly image small — a blocked source is documented, not force-cracked).

`RawItem.payload_hint` carries `discovery_path` ∈ {feed,sitemap,html} (+ optional
`source_rank`) so the outbox records how each item was found.
"""

from __future__ import annotations

import hashlib
import time
from typing import Any, cast

import structlog
from defusedxml import ElementTree as ET
from defusedxml.ElementTree import ParseError

from app.ingestion.framework.allowlist import assert_host_allowed
from app.ingestion.framework.base_adapter import RawItem
from app.ingestion.framework.exceptions import (
    AdapterBlockedError,
    BodyTooLargeError,
    RobotsTxtDisallow,
)
from app.ingestion.framework.registry_adapter import RegistryAdapter
from app.ingestion.framework.robots import is_allowed as robots_is_allowed
from app.ingestion.framework.scraping_rate_limit import acquire_scrape_slot

logger = structlog.get_logger(__name__)

_UA = "SaferSkillsBot/1.0 (+https://saferskills.ai/bot)"
_FROM = "bot@saferskills.ai"
_DEFAULT_IMPERSONATE = "chrome131"

# 25 MiB — parity with the HTTPX `_body_size_cap_hook` (security.md #3). curl_cffi
# bypasses that response hook, so the scrape tier enforces the cap itself.
_MAX_BODY_BYTES = 26_214_400

# Body markers that indicate a Cloudflare challenge interstitial (vs the real page).
_CF_BODY_MARKERS = (
    "just a moment",
    "challenge-platform",
    "cf-chl",
    "_cf_chl_opt",
    "checking your browser",
    "enable javascript and cookies to continue",
)


def is_cloudflare_challenge(status: int, headers: dict[str, str], text: str) -> bool:
    """Heuristic: does this response look like a Cloudflare bot-challenge interstitial?

    `headers` must be a lowercased-key mapping. We treat it as a challenge when the
    `cf-mitigated: challenge` header is present, OR a 403/503 served by Cloudflare
    carries a known challenge body marker, OR the body itself carries the
    challenge-platform script signature (some challenges return 200)."""
    if headers.get("cf-mitigated", "").lower() == "challenge":
        return True
    low = text.lower()
    server = headers.get("server", "").lower()
    if status in (403, 503) and "cloudflare" in server:
        return any(m in low for m in _CF_BODY_MARKERS)
    return "challenge-platform" in low and "cf-chl" in low


def _err_reason(status: int) -> str | None:
    if status == 200:
        return None
    if status in (429, 403):
        return "rate_limit"
    if status >= 500:
        return "http_5xx"
    return "other"


class ScrapingAdapter(RegistryAdapter):
    """Base for scraped-aggregator adapters. Subclasses implement list_items/normalize."""

    @property
    def _impersonate(self) -> str:
        return str(self.config.discovery.get("impersonate", _DEFAULT_IMPERSONATE))

    # -- Discovery precedence helpers ------------------------------

    async def _fetch_feed(self, client: Any, url: str) -> Any | None:
        """Tier-0 JSON-feed fetch via the inherited HTTPX client (SSRF + Hishel safe).

        Returns the parsed JSON on 200, else None (the caller falls back to sitemap
        / HTML). Network + decode errors are swallowed to None."""
        try:
            r = await client.get(url)
        except Exception:
            logger.debug("scrape.feed_fetch_failed", source=self.source_name, url=url)
            return None
        if r.status_code != 200:
            return None
        try:
            return r.json()
        except Exception:
            logger.debug("scrape.feed_decode_failed", source=self.source_name, url=url)
            return None

    async def _fetch_sitemap_urls(self, client: Any, url: str) -> list[str]:
        """Tier-0 sitemap fetch via the inherited HTTPX client; returns the `<loc>`
        URLs (empty on any failure). Handles both urlset + sitemapindex documents."""
        try:
            r = await client.get(url)
        except Exception:
            logger.debug("scrape.sitemap_fetch_failed", source=self.source_name, url=url)
            return []
        if r.status_code != 200:
            return []
        try:
            root = ET.fromstring(r.content)
        except ParseError, ValueError:
            return []
        locs: list[str] = []
        for el in root.iter():
            if el.tag.rsplit("}", 1)[-1] == "loc" and el.text:
                locs.append(el.text.strip())
        return locs

    async def _fetch_html(
        self,
        url: str,
        *,
        discovery_path: str = "html",
        source_rank: int | None = None,
    ) -> RawItem:
        """Tier-1 browser-impersonating HTML fetch (curl_cffi). Self-enforces the
        SSRF allowlist + per-source rate limit + robots.txt (this client bypasses the
        HTTPX transport hooks). Raises `RobotsTxtDisallow` when robots forbids the
        path and `AdapterBlockedError` on a Cloudflare challenge. Other failures
        return a RawItem carrying the status + `error_reason` (no raise)."""
        from curl_cffi.requests import AsyncSession

        assert_host_allowed(url, self.source_hosts)
        if not await robots_is_allowed(url, user_agent=_UA):
            raise RobotsTxtDisallow(f"robots.txt disallows {url}")
        await acquire_scrape_slot(self.source_name, self.rate_limit_per_second)

        started = time.monotonic()
        try:
            async with AsyncSession() as session:
                r = await session.get(
                    url,
                    # curl_cffi types `impersonate` as a closed Literal of browser
                    # tags; we read it from YAML (a plain str), so cast past the Literal.
                    impersonate=cast("Any", self._impersonate),
                    headers={"User-Agent": _UA, "From": _FROM},
                    timeout=60,
                )
        except Exception:
            logger.debug("scrape.html_fetch_failed", source=self.source_name, url=url)
            return RawItem(
                source_id=url,
                raw_body_bytes=b"",
                raw_body_hash=hashlib.sha256(b"").hexdigest(),
                http_status=0,
                fetch_tier=1,
                error_reason="timeout",
                payload_hint={"url": url, "discovery_path": discovery_path},
            )

        headers = {str(k).lower(): str(v) for k, v in dict(r.headers).items()}
        text = r.text or ""
        if is_cloudflare_challenge(r.status_code, headers, text):
            raise AdapterBlockedError(f"cloudflare challenge at {url}")

        body = r.content or b""
        # curl_cffi bypasses the HTTPX `_body_size_cap_hook`, so enforce the 25 MiB
        # cap here too. The body is already fully buffered by curl_cffi, so
        # this is a post-hoc guard; it raises the same IngestionError the HTTPX tier
        # raises (caught by the cycle wrapper → clean WARN + failed run).
        if len(body) > _MAX_BODY_BYTES:
            raise BodyTooLargeError(f"BODY TOO LARGE: {len(body)} bytes from {url}")
        payload_hint: dict[str, Any] = {
            "url": url,
            "html": text,
            "discovery_path": discovery_path,
        }
        if source_rank is not None:
            payload_hint["source_rank"] = source_rank
        return RawItem(
            source_id=url,
            raw_body_bytes=body,
            raw_body_hash=hashlib.sha256(body).hexdigest(),
            http_status=r.status_code,
            duration_ms=int((time.monotonic() - started) * 1000),
            fetch_tier=1,
            payload_hint=payload_hint,
            error_reason=_err_reason(r.status_code),
        )

    def extract_main_content(self, html: str) -> str:
        """Extract the readable main-content text from an HTML page (descriptions).

        Trafilatura wrapper — returns "" when nothing extractable. Bounded by the
        caller to the ≤280-char description cap (ToS-respect #3)."""
        if not html:
            return ""
        try:
            import trafilatura

            extracted = trafilatura.extract(html, include_comments=False, include_tables=False)
            return (extracted or "").strip()
        except Exception:
            logger.debug("scrape.extract_failed", source=self.source_name)
            return ""

    @staticmethod
    def raw_from_record(
        record: dict[str, Any],
        *,
        source_id: str,
        discovery_path: str,
        source_rank: int | None = None,
    ) -> RawItem:
        """Build a 200 RawItem from an already-parsed feed/listing record, tagging it
        with its `discovery_path` (+ optional `source_rank`) for the outbox."""
        import json

        body = json.dumps(record, separators=(",", ":"), sort_keys=True, default=str).encode()
        payload_hint: dict[str, Any] = {**record, "discovery_path": discovery_path}
        if source_rank is not None:
            payload_hint["source_rank"] = source_rank
        return RawItem(
            source_id=source_id,
            raw_body_bytes=body,
            raw_body_hash=hashlib.sha256(body).hexdigest(),
            http_status=200,
            fetch_tier=1,
            payload_hint=payload_hint,
        )
