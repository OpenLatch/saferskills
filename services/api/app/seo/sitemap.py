"""Sitemap corpus queries + XML builders.

The backend owns the sitemap index and the DB-backed shards (items / scans /
agents); the webapp owns the `static` shard (its prerendered marketing + docs
routes, which the backend cannot enumerate). Every query enumerates ONLY
`visibility='public'` + COMPLETED rows and excludes the bulk auto-scan firehose
— see `.claude/rules/security.md` § Public-input handling and the prime
invariant in the I-07 design doc.

`lastmod` is always a REAL maintained timestamp (a row's `scanned_at`), never
`now()` — a "today on everything" lastmod makes Google ignore the field (R6).
"""

from __future__ import annotations

from datetime import datetime
from xml.sax.saxutils import escape

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.generated.agent_run import AgentRun
from app.models.generated.catalog_item import CatalogItem
from app.models.generated.scan import Scan
from app.models.generated.scan_run import ScanRun
from app.scan.constants import FEED_EXCLUDED_SOURCES

# Hard sitemap-protocol limit: 50,000 URLs / 50 MB per file. 50k slug+lastmod
# entries is a few MB, comfortably under the byte cap.
SHARD_SIZE = 50_000

# The section name → query map. The route layer fans `items-1`, `scans-2`, ...
# onto these by splitting the trailing page index.
SECTIONS = ("items", "scans", "agents")

Entry = tuple[str, datetime]


async def _items(session: AsyncSession) -> list[Entry]:
    """Public catalog items that ALREADY carry COMPLETED scan data (D-07-03).

    "Completed" == `Scan.tier != 'unscoped'`. A pending / placeholder Scan row is
    `aggregate_score=0, tier='unscoped'` and `aggregate_score` is NON-nullable, so
    an `aggregate_score IS NOT NULL` check would wrongly admit thin / running
    pages. `lastmod` = MAX(`scanned_at`) of the item's completed scans (a
    maintained timestamp; `CatalogItem.updated_at` is not reliably stamped on
    interactive / vendor completion).
    """
    stmt = (
        select(CatalogItem.slug, func.max(Scan.scanned_at))
        .join(Scan, Scan.catalog_item_id == CatalogItem.id)
        .where(CatalogItem.archived.is_(False), CatalogItem.visibility == "public")
        .where(Scan.tier != "unscoped")
        .group_by(CatalogItem.id, CatalogItem.slug)
        # Stable tiebreaker on slug — `scanned_at` is non-unique, and rows tied
        # around the 50k shard boundary must not shift between separate shard HTTP
        # requests (else a row lands in two shards or none).
        .order_by(func.max(Scan.scanned_at).desc(), CatalogItem.slug.asc())
    )
    rows = (await session.execute(stmt)).all()
    return [(f"/items/{slug}", ts) for slug, ts in rows]


async def _scans(session: AsyncSession) -> list[Entry]:
    """Public, COMPLETED repo runs, excluding the bulk firehose (D-07-03).

    `status == 'completed'` is REQUIRED: `scan_runs.status` defaults `'pending'`
    and a public submission row exists BEFORE it finishes — without the filter a
    pending / failed run would leak into the sitemap. `lastmod` = `scanned_at`.
    """
    stmt = (
        select(ScanRun.id, ScanRun.scanned_at)
        .where(ScanRun.visibility == "public")
        .where(ScanRun.status == "completed")
        .where(ScanRun.source.notin_(FEED_EXCLUDED_SOURCES))
        # Stable id tiebreaker (non-unique scanned_at) for shard-boundary safety.
        .order_by(ScanRun.scanned_at.desc(), ScanRun.id.desc())
    )
    rows = (await session.execute(stmt)).all()
    return [(f"/scans/{rid}", ts) for rid, ts in rows]


async def _agents(session: AsyncSession) -> list[Entry]:
    """Public, graded Agent Reports only (mirror `directory._public_graded`).

    `AgentRun` has no `scanned_at`-only timestamp guarantee — `scanned_at` is
    nullable (set at grade time) while `created_at` is non-nullable — so
    `lastmod` coalesces to `created_at` for a freshly graded run that has no
    `scanned_at` yet, and ordering is on the always-present `created_at`.
    """
    stmt = (
        select(AgentRun.id, func.coalesce(AgentRun.scanned_at, AgentRun.created_at))
        .where(AgentRun.visibility == "public")
        .where(AgentRun.status.in_(("graded", "published")))
        .where(AgentRun.score.is_not(None))
        # Order by the same coalesced lastmod (created_at is non-null) with a
        # stable id tiebreaker for shard-boundary safety.
        .order_by(
            func.coalesce(AgentRun.scanned_at, AgentRun.created_at).desc(),
            AgentRun.id.desc(),
        )
    )
    rows = (await session.execute(stmt)).all()
    return [(f"/agents/{rid}", ts) for rid, ts in rows]


_QUERIES = {"items": _items, "scans": _scans, "agents": _agents}


async def section_entries(session: AsyncSession, section: str) -> list[Entry]:
    """All entries for a section (`items` / `scans` / `agents`). Raises KeyError
    for an unknown section — the route maps that to a 404."""
    return await _QUERIES[section](session)


async def section_count(session: AsyncSession, section: str) -> int:
    """Row count for a section — used to compute the shard count in the index."""
    # Cheapest correct count: run the query and len() it. The result sets are
    # bounded by the public corpus and the query is indexed; a separate COUNT
    # subquery would have to re-derive the same GROUP BY / filter, so re-using the
    # entry list keeps the two definitions identical (no drift between count and
    # the shard a crawler then fetches).
    return len(await section_entries(session, section))


def _iso(ts: datetime) -> str:
    """ISO-8601 lastmod. Naive timestamps are treated as already-UTC."""
    return ts.isoformat()


def urlset(entries: list[Entry], origin: str) -> str:
    """Render a `<urlset>` for a shard window. An empty window → a valid empty
    urlset (NOT a 404)."""
    origin = origin.rstrip("/")
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ]
    for path, ts in entries:
        loc = escape(f"{origin}{path}")
        parts.append(f"<url><loc>{loc}</loc><lastmod>{_iso(ts)}</lastmod></url>")
    parts.append("</urlset>")
    return "".join(parts)


def index(shard_names: list[str], origin: str) -> str:
    """Render a `<sitemapindex>` referencing `{origin}/sitemaps/{name}.xml` for
    each shard. The webapp-owned `static` shard is included first by the caller.

    No `<lastmod>` on the `<sitemap>` entries: a per-request `now()` is not a
    real material-change timestamp, and a synthetic index lastmod makes Google
    ignore the field (R6). The valuable lastmod is on each shard's `<url>`
    (`urlset`), which carries the row's real `scanned_at`."""
    origin = origin.rstrip("/")
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ]
    for name in shard_names:
        loc = escape(f"{origin}/sitemaps/{name}.xml")
        parts.append(f"<sitemap><loc>{loc}</loc></sitemap>")
    parts.append("</sitemapindex>")
    return "".join(parts)


def shard_count(row_count: int) -> int:
    """Number of shards for a section of `row_count` rows. A section with 0 rows
    still gets 1 shard (a valid empty urlset), so the index always lists it and a
    crawler never hits a 404 for an advertised shard."""
    if row_count <= 0:
        return 1
    return (row_count + SHARD_SIZE - 1) // SHARD_SIZE


async def index_shard_names(session: AsyncSession) -> list[str]:
    """The DB-shard names the index lists, e.g. `['items-1', 'scans-1', ...]`.
    The webapp-owned `static` shard is prepended by the route layer."""
    names: list[str] = []
    for section in SECTIONS:
        count = await section_count(session, section)
        for page in range(1, shard_count(count) + 1):
            names.append(f"{section}-{page}")
    return names
