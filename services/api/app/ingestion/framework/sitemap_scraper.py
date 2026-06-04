"""SitemapHtmlAdapter — sitemap-driven HTML aggregator scraper (I-04 Phase B PR2).

The 7 aggregator HTML sources (mcp.so, pulsemcp, clawhub, skillsmp, skills.sh,
claudeskills.info, skillhub.club) share one shape: a sitemap (often a sitemap-index)
enumerates item-detail URLs, each item page is server-rendered with `og:` meta + a
GitHub repo link. This base encodes that shape once; every per-site difference lives
in the YAML `discovery` block, so each adapter module is a one-line registration.

It reuses the PR1 ScrapingAdapter primitives wholesale: `_fetch_html` (curl_cffi
browser impersonation — required because most of these hosts are Cloudflare-proxied
and reject plain HTTPX) already enforces the SSRF allowlist + per-source rate limit
+ robots.txt + Cloudflare-challenge detection. A genuinely blocked host raises
`AdapterBlockedError` → the cycle wrapper flips it to `status='blocked'`. An
unreachable host (e.g. clawhub's dead DNS) yields zero items and is logged, never
crashes.

`discovery` config (all optional unless noted):
  sitemap_url          (required) the entry sitemap (index or urlset)
  item_sitemap_substr  list[str] — when the entry is a sitemap-index, only recurse
                       into child sitemaps whose URL contains one of these (e.g.
                       ["projects"], ["skills"]). Empty = recurse all children.
  item_url_regex       (required) a regex; only `<loc>`s matching it are item pages
  kind                 catalog kind hint ("mcp_server" | "skill")
  name_from            "og_title" (default) | "slug" — where the display name comes from
  name_strip           list[str] — substrings/suffixes stripped from an og:title
  github_denylist      list[str] — "org/repo" values to skip (site's own repo, nav links)
  max_items            cap on item pages fetched per cycle (default 200)
"""

from __future__ import annotations

import re
from collections.abc import AsyncIterator
from typing import Any, cast

import structlog
from bs4 import BeautifulSoup
from defusedxml import ElementTree as ET
from defusedxml.ElementTree import ParseError

from app.ingestion.framework.base_adapter import NormalizedItem, RawItem
from app.ingestion.framework.github_enrich import enrich_repo_facts, parse_github_coords
from app.ingestion.framework.scraping_adapter import ScrapingAdapter

logger = structlog.get_logger(__name__)

_GITHUB_RE = re.compile(r"github\.com/([A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9][A-Za-z0-9_.-]*)")
# Repo paths that are never the artifact's own repo — GitHub product pages, common
# nav/footer links, and the MCP spec/registry repos that aggregators link in their
# chrome. Augmented per-site via `github_denylist`. NOTE: `modelcontextprotocol/servers`
# is intentionally NOT here — it is a real reference-server monorepo (a valid artifact).
_GLOBAL_GH_DENYLIST = frozenset(
    {
        "github/codeql-action",
        "actions/checkout",
        "sponsors/explore",
        "features/copilot",
        "features/actions",
        "about/diversity",
        "modelcontextprotocol/registry",
        "modelcontextprotocol/modelcontextprotocol",
        "modelcontextprotocol/docs",
    }
)


def _locs(xml: str) -> list[str]:
    """All `<loc>` URLs from a sitemap (index or urlset). [] on parse failure."""
    try:
        root = ET.fromstring(xml.encode())
    except ParseError, ValueError:
        return []
    out: list[str] = []
    for el in root.iter():
        if el.tag.rsplit("}", 1)[-1] == "loc" and el.text:
            out.append(el.text.strip())
    return out


def _is_index(xml: str) -> bool:
    return "<sitemapindex" in xml[:4000].lower()


def _meta(soup: BeautifulSoup, *keys: str) -> str | None:
    """First matching <meta property|name=key content=...>, by precedence."""
    for key in keys:
        for attr in ("property", "name"):
            tag = soup.find("meta", attrs={attr: key})
            if tag is not None:
                content = tag.get("content")  # type: ignore[union-attr]
                if isinstance(content, str) and content.strip():
                    return content.strip()
    return None


class SitemapHtmlAdapter(ScrapingAdapter):
    """Configurable sitemap→item-page HTML scraper. Subclasses only register a name."""

    # -- discovery accessors --------------------------------------------------
    @property
    def _sitemap_url(self) -> str:
        return str(self.config.discovery["sitemap_url"])

    @property
    def _item_sitemap_substr(self) -> list[str]:
        return list(self.config.discovery.get("item_sitemap_substr") or [])

    @property
    def _item_url_re(self) -> re.Pattern[str]:
        return re.compile(str(self.config.discovery["item_url_regex"]))

    @property
    def _kind(self) -> str:
        return str(self.config.discovery.get("kind", "mcp_server"))

    @property
    def _name_from(self) -> str:
        return str(self.config.discovery.get("name_from", "og_title"))

    @property
    def _name_strip(self) -> list[str]:
        return list(self.config.discovery.get("name_strip") or [])

    @property
    def _gh_denylist(self) -> frozenset[str]:
        raw = cast("list[Any]", self.config.discovery.get("github_denylist") or [])
        extra = {str(x).lower() for x in raw}
        return frozenset(_GLOBAL_GH_DENYLIST | extra)

    @property
    def _max_items(self) -> int:
        return int(self.config.discovery.get("max_items", 200))

    # -- discovery ------------------------------------------------------------
    async def _get_html(self, url: str) -> tuple[int, str]:
        """Fetch a page via curl_cffi (allowlist + rate-limit + robots + CF-detect).
        Returns (status, html). Network failure → (0, '') (no raise)."""
        raw = await self._fetch_html(url)
        return raw.http_status, str(raw.payload_hint.get("html") or "")

    async def _item_urls(self, client: Any) -> list[str]:
        """Resolve the entry sitemap (recursing one level into matching child sitemaps),
        return the item-detail URLs, capped at max_items."""
        status, xml = await self._get_html(self._sitemap_url)
        if status != 200 or not xml:
            logger.info("scrape.sitemap_unreachable", source=self.source_name, status=status)
            return []
        locs = _locs(xml)
        item_re = self._item_url_re
        items: list[str] = []
        if _is_index(xml):
            substrs = self._item_sitemap_substr
            children = [u for u in locs if not substrs or any(sub in u for sub in substrs)]
            for child in children:
                if len(items) >= self._max_items:
                    break
                cstatus, cxml = await self._get_html(child)
                if cstatus != 200 or not cxml:
                    continue
                items.extend(u for u in _locs(cxml) if item_re.search(u))
        else:
            items = [u for u in locs if item_re.search(u)]
        # Dedup preserving order, then cap.
        seen: set[str] = set()
        deduped = [u for u in items if not (u in seen or seen.add(u))]
        return deduped[: self._max_items]

    async def list_items(self, client: Any) -> AsyncIterator[RawItem]:
        for url in await self._item_urls(client):
            raw = await self._fetch_html(url, discovery_path="sitemap")
            raw.source_id = f"{self.source_name}/{url}"
            raw.payload_hint["item_url"] = url
            yield raw

    # -- normalize ------------------------------------------------------------
    def _extract_github(self, html: str) -> tuple[str | None, str | None]:
        deny = self._gh_denylist
        for m in _GITHUB_RE.finditer(html):
            slug = m.group(1).removesuffix(".git").rstrip("/")
            if slug.lower() in deny:
                continue
            org, repo = parse_github_coords(f"https://github.com/{slug}")
            if org and repo:
                return org, repo
        return None, None

    def _extract_name(self, soup: BeautifulSoup, item_url: str) -> str:
        if self._name_from == "slug":
            # `name_slug_index` picks which path segment is the name (default -1 =
            # last; mcp.so uses -2 because its URLs are /server/<name>/<author>).
            idx = int(self.config.discovery.get("name_slug_index", -1))
            segs = [s for s in item_url.rstrip("/").split("/") if s]
            seg = segs[idx] if segs and -len(segs) <= idx < len(segs) else item_url
            return seg.replace("-", " ").strip() or item_url
        title = _meta(soup, "og:title") or (soup.title.string if soup.title else "") or ""
        title = title.strip()
        for s in self._name_strip:
            title = title.replace(s, "")
        # Drop a trailing " | Site" / " - Site" branding segment if still present
        # (separators: pipe, hyphen, or the en/em dashes U+2013/U+2014).
        title = re.split(r"\s+[|–—-]\s+", title)[0].strip()  # noqa: RUF001
        if not title:
            seg = item_url.rstrip("/").rsplit("/", 1)[-1]
            title = seg.replace("-", " ").strip()
        return title or item_url

    def normalize(self, raw: RawItem) -> NormalizedItem | None:
        if raw.http_status != 200:
            return None
        html = str(raw.payload_hint.get("html") or "")
        item_url = str(raw.payload_hint.get("item_url") or raw.source_id)
        if not html:
            return None
        soup = BeautifulSoup(html, "lxml")
        name = self._extract_name(soup, item_url)
        if not name:
            return None  # unexpected DOM — fail gracefully (skipped, logged via outbox)
        github_org, github_repo = self._extract_github(html)
        github_url = (
            f"https://github.com/{github_org}/{github_repo}" if github_org and github_repo else None
        )
        description = (_meta(soup, "og:description", "description") or "")[:280]
        return NormalizedItem(
            github_org=github_org,
            github_repo=github_repo,
            display_name=name[:200],
            description=description,
            github_url=github_url,
            source_url=item_url,  # backlink credits the aggregator listing (ToS #4)
            kind=self._kind,
            metadata_files={},
            aggregator_listings=[self.config.name],
        )

    async def enrich(self, client: Any, normalized: NormalizedItem) -> None:
        await enrich_repo_facts(client, normalized)
