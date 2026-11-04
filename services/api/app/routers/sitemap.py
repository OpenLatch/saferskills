"""Public sitemap surface (`/api/v1/sitemap/*`).

Backend-generated, DB-backed sitemap index + shards. The webapp relays these at
the apex (`/sitemap.xml`, `/sitemaps/<shard>.xml`) so crawlers see clean
`https://saferskills.ai/...` URLs (D-07-01). Enumerates ONLY `visibility='public'`
+ completed rows, never a `share_token` URL — see `.claude/rules/security.md`
§ Public-input handling.

Cache-on-read (D-07-02): `Cache-Control: public, max-age=3600`. Each shard reads only
its window through the section's index; the index counts sections and is cached.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.ttl_cache import TtlCache
from app.db.session import SessionFactory, get_session, get_session_factory
from app.seo import sitemap

router = APIRouter(prefix="/sitemap", tags=["seo"])

# Matches the index's max-age. Crawlers fetch it rarely, but one uncached fetch
# walks every section, so overlapping fetches must not each run that.
_index_cache: TtlCache[str] = TtlCache(name="sitemap_index", ttl_s=3600.0)

_CACHE_HEADERS = {"Cache-Control": "public, max-age=3600"}
_XML = "application/xml"


@router.get("/index.xml")
async def sitemap_index(
    session_factory: SessionFactory = Depends(get_session_factory),
) -> Response:
    """The `<sitemapindex>`. Always lists the webapp-owned `static` shard first,
    then one shard per ≤50k rows of items / scans / agents."""
    origin = get_settings().saferskills_site_origin

    async def load() -> str:
        async with session_factory() as session:
            db_shards = await sitemap.index_shard_names(session)
        return sitemap.index(["static", *db_shards], origin)

    xml = await _index_cache.get(load)
    return Response(xml, media_type=_XML, headers=_CACHE_HEADERS)


@router.get("/shard/{name}.xml")
async def sitemap_shard(name: str, session: AsyncSession = Depends(get_session)) -> Response:
    """A single shard `<urlset>`. `name` is `<section>-<page>` (e.g. `items-1`).
    An out-of-range / empty page renders a valid empty urlset; an unknown section
    or a malformed page index → 404."""
    origin = get_settings().saferskills_site_origin
    section, _, page = name.partition("-")
    if section not in sitemap.SECTIONS:
        raise HTTPException(status_code=404, detail="unknown sitemap section")
    try:
        page_n = int(page) if page else 1
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="malformed sitemap shard") from exc
    if page_n < 1:
        raise HTTPException(status_code=404, detail="malformed sitemap shard")

    entries = await sitemap.section_entries(session, section, page=page_n)
    xml = sitemap.urlset(entries, origin)
    return Response(xml, media_type=_XML, headers=_CACHE_HEADERS)
