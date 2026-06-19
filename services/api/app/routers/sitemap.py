"""Public sitemap surface (`/api/v1/sitemap/*`).

Backend-generated, DB-backed sitemap index + shards. The webapp relays these at
the apex (`/sitemap.xml`, `/sitemaps/<shard>.xml`) so crawlers see clean
`https://saferskills.ai/...` URLs (D-07-01). Enumerates ONLY `visibility='public'`
+ completed rows, never a `share_token` URL — see `.claude/rules/security.md`
§ Public-input handling.

Cache-on-read (D-07-02): `Cache-Control: public, max-age=3600`; the query is
indexed and regenerates on a cache miss — no materialized table to keep in sync.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.session import get_session
from app.seo import sitemap

router = APIRouter(prefix="/sitemap", tags=["seo"])

_CACHE_HEADERS = {"Cache-Control": "public, max-age=3600"}
_XML = "application/xml"


@router.get("/index.xml")
async def sitemap_index(session: AsyncSession = Depends(get_session)) -> Response:
    """The `<sitemapindex>`. Always lists the webapp-owned `static` shard first,
    then one shard per ≤50k rows of items / scans / agents."""
    origin = get_settings().saferskills_site_origin
    db_shards = await sitemap.index_shard_names(session)
    shard_names = ["static", *db_shards]
    xml = sitemap.index(shard_names, origin)
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

    entries = await sitemap.section_entries(session, section)
    window = entries[(page_n - 1) * sitemap.SHARD_SIZE : page_n * sitemap.SHARD_SIZE]
    xml = sitemap.urlset(window, origin)
    return Response(xml, media_type=_XML, headers=_CACHE_HEADERS)
