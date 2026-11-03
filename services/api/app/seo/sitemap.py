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
from typing import Any
from xml.sax.saxutils import escape

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.generated.agent_run import AgentRun
from app.models.generated.catalog_item import CatalogItem
from app.models.generated.scan_run import ScanRun
from app.queries import LISTED_ITEM
from app.scan.constants import FEED_EXCLUDED_SOURCES

# Hard sitemap-protocol limit: 50,000 URLs / 50 MB per file. 50k slug+lastmod
# entries is a few MB, comfortably under the byte cap.
SHARD_SIZE = 50_000

# The section name → query map. The route layer fans `items-1`, `scans-2`, ...
# onto these by splitting the trailing page index.
SECTIONS = ("items", "scans", "agents")

Entry = tuple[str, datetime]


# Each section is one (path, lastmod) query, ordered for stable shard windows. Sharing it
# keeps the count and the entries from disagreeing. Every order has a unique tiebreaker,
# because `scanned_at` isn't unique and rows tied around a 50k shard boundary must not
# shift between separate shard requests (else a row lands in two shards or none).
_QUERIES: dict[str, tuple[Select[Any], str]] = {
    # Public catalog items that ALREADY carry COMPLETED scan data (D-07-03).
    # `latest_scan_*` only ever points at a scan with `tier != 'unscoped'`, so a pending
    # placeholder can't admit a thin page. `lastmod` is that scan's `scanned_at` (a
    # maintained timestamp; `updated_at` isn't reliably stamped on scan completion).
    "items": (
        select(CatalogItem.slug, CatalogItem.latest_scanned_at)
        .where(LISTED_ITEM)
        .where(CatalogItem.latest_scanned_at.is_not(None))
        .order_by(CatalogItem.latest_scanned_at.desc(), CatalogItem.slug.asc()),
        "/items/{}",
    ),
    # Public, COMPLETED repo runs, excluding the bulk firehose (D-07-03). `status` is
    # REQUIRED: `scan_runs.status` defaults `'pending'` and a public submission row exists
    # BEFORE it finishes, so a pending or failed run would otherwise leak in.
    "scans": (
        select(ScanRun.id, ScanRun.scanned_at)
        .where(ScanRun.visibility == "public")
        .where(ScanRun.status == "completed")
        .where(ScanRun.source.notin_(FEED_EXCLUDED_SOURCES))
        .order_by(ScanRun.scanned_at.desc(), ScanRun.id.desc()),
        "/scans/{}",
    ),
    # Public, graded Agent Reports only (mirror `directory._public_graded`). `scanned_at`
    # is nullable (set at grade time), so `lastmod` coalesces to `created_at`.
    "agents": (
        select(AgentRun.id, func.coalesce(AgentRun.scanned_at, AgentRun.created_at))
        .where(AgentRun.visibility == "public")
        .where(AgentRun.status.in_(("graded", "published")))
        .where(AgentRun.score.is_not(None))
        .order_by(
            func.coalesce(AgentRun.scanned_at, AgentRun.created_at).desc(),
            AgentRun.id.desc(),
        ),
        "/agents/{}",
    ),
}


async def section_entries(session: AsyncSession, section: str, *, page: int = 1) -> list[Entry]:
    """One shard's entries (`page` is 1-based), fetched with LIMIT/OFFSET so a request
    reads only its window. Raises KeyError for an unknown section; the route maps that
    to a 404. Shard bodies aren't cached: each is several MB, on small machines."""
    query, path = _QUERIES[section]
    stmt = query.offset((page - 1) * SHARD_SIZE).limit(SHARD_SIZE)
    rows = (await session.execute(stmt)).all()
    return [(path.format(key), ts) for key, ts in rows]


async def section_count(session: AsyncSession, section: str) -> int:
    """Row count for a section — used to compute the shard count in the index."""
    query, _ = _QUERIES[section]
    count = select(func.count()).select_from(query.order_by(None).subquery())
    return int((await session.execute(count)).scalar_one())


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
