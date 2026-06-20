"""Sitemap surface — public-only, completed-only enumeration (I-07 plan 01).

Asserts the index lists `static` + the DB shards, and each shard excludes the
unlisted / pending / failed / firehose rows while including a real completed
public scan. `lastmod` reflects the row's real `scanned_at`, never `now()`.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from xml.etree.ElementTree import Element

import pytest
from defusedxml.ElementTree import fromstring as safe_fromstring
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.catalog_item import CatalogItem
from app.models.generated.agent_run import AgentRun
from app.models.scan import Scan
from app.models.scan_run import ScanRun

_NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}


def _parse(text: str) -> Element:
    """XXE-safe parse (defusedxml) returning a typed stdlib Element."""
    return safe_fromstring(text)


def _loc_texts(root: Element, path: str) -> list[str]:
    """All non-None element texts at `path`."""
    return [el.text for el in root.findall(path, _NS) if el.text]


def _entries(root: Element) -> dict[str, str]:
    """`{<loc> → <lastmod>}` for every `<url>` in a urlset."""
    out: dict[str, str] = {}
    for url in root.findall("sm:url", _NS):
        loc = url.find("sm:loc", _NS)
        lastmod = url.find("sm:lastmod", _NS)
        if loc is not None and loc.text:
            out[loc.text] = lastmod.text if (lastmod is not None and lastmod.text) else ""
    return out


def _make_agent_run(
    *, visibility: str = "public", status: str = "graded", score: int | None = 72
) -> AgentRun:
    return AgentRun(
        status=status,
        agent_name="claude-code",
        runtime="claude-code",
        band="green",
        score=score,
        pack_id="p",
        pack_version="v",
        visibility=visibility,
        rubric_version="r",
        engine_version="e",
        latency_ms=0,
        idempotency_key=uuid.uuid4().hex,
        nonce="n",
        share_token=(uuid.uuid4().hex if visibility == "unlisted" else None),
    )


def _make_item(slug: str, *, visibility: str = "public", archived: bool = False) -> CatalogItem:
    return CatalogItem(
        kind="skill",
        slug=slug,
        display_name=slug,
        github_url=f"https://github.com/acme/{slug}",
        github_org="acme",
        github_repo=slug,
        default_branch="main",
        popularity_tier="indexed",
        popularity_score=1,
        agent_compatibility=[],
        sources=[],
        visibility=visibility,
        archived=archived,
    )


def _make_scan(item_id: uuid.UUID, *, tier: str, scanned_at: datetime, score: int = 80) -> Scan:
    return Scan(
        catalog_item_id=item_id,
        idempotency_key=uuid.uuid4().hex,
        github_url="https://github.com/acme/repo",
        ref_sha="a" * 40,
        aggregate_score=score,
        tier=tier,
        sub_scores={},
        score_breakdown={},
        rubric_version="abc1234",
        engine_version="def5678",
        latency_ms=10,
        source="submission",
        scanned_at=scanned_at,
    )


def _make_run(
    *,
    source: str = "submission",
    visibility: str = "public",
    status: str = "completed",
    scanned_at: datetime | None = None,
) -> ScanRun:
    return ScanRun(
        idempotency_key=uuid.uuid4().hex,
        github_url="https://github.com/acme/repo",
        ref_sha=None,
        repo_aggregate_score=80,
        repo_tier="green",
        kind_tally={"skill": 1},
        capability_count=1,
        rubric_version="abc1234",
        engine_version="def5678",
        source=source,
        latency_ms=10,
        file_count=1,
        status=status,
        visibility=visibility,
        source_kind="github",
        scanned_at=scanned_at or datetime.now(tz=UTC),
    )


@pytest.mark.asyncio
async def test_index_lists_all_shards(db_client: AsyncClient, db_session: AsyncSession) -> None:
    resp = await db_client.get("/api/v1/sitemap/index.xml")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/xml")
    assert resp.headers["cache-control"] == "public, max-age=3600"

    root = _parse(resp.text)
    locs = _loc_texts(root, ".//sm:sitemap/sm:loc")
    # static is always first; one shard per section even when empty.
    assert any(loc.endswith("/sitemaps/static.xml") for loc in locs)
    assert any(loc.endswith("/sitemaps/items-1.xml") for loc in locs)
    assert any(loc.endswith("/sitemaps/scans-1.xml") for loc in locs)
    assert any(loc.endswith("/sitemaps/agents-1.xml") for loc in locs)
    # No synthetic <lastmod> on the index (R6: a per-request now() isn't a real
    # material-change mtime → Google ignores the field). The real lastmod lives
    # on each shard's <url>.
    assert "<lastmod>" not in resp.text


@pytest.mark.asyncio
async def test_shard_excludes_unlisted_pending_and_firehose(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    ts = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)
    good = _make_run(source="submission", scanned_at=ts)
    db_session.add_all(
        [
            good,
            _make_run(source="submission", visibility="unlisted"),
            _make_run(source="submission", status="pending"),
            _make_run(source="submission", status="failed"),
            _make_run(source="ingestion"),
            _make_run(source="rescan_rules"),
        ]
    )
    await db_session.flush()

    resp = await db_client.get("/api/v1/sitemap/shard/scans-1.xml")
    assert resp.status_code == 200
    entries = _entries(_parse(resp.text))
    good_loc = next(loc for loc in entries if loc.endswith(f"/scans/{good.id}"))
    # The completed public submission is present with its real scanned_at lastmod.
    assert "2026-01-02" in entries[good_loc]
    # No /scans/r/ token URL ever appears.
    assert not any("/scans/r/" in loc for loc in entries)
    # Exactly one entry — every other seeded run is excluded.
    assert len(entries) == 1


@pytest.mark.asyncio
async def test_items_shard_requires_completed_scan(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    suffix = uuid.uuid4().hex[:8]
    scored = _make_item(f"acme--scored-{suffix}")
    never = _make_item(f"acme--never-{suffix}")
    placeholder = _make_item(f"acme--placeholder-{suffix}")
    db_session.add_all([scored, never, placeholder])
    await db_session.flush()

    ts = datetime(2026, 3, 4, 5, 6, 7, tzinfo=UTC)
    db_session.add_all(
        [
            _make_scan(scored.id, tier="green", scanned_at=ts),
            # placeholder = an unscoped scan row (score 0, tier unscoped).
            _make_scan(placeholder.id, tier="unscoped", scanned_at=datetime.now(tz=UTC), score=0),
        ]
    )
    await db_session.flush()

    resp = await db_client.get("/api/v1/sitemap/shard/items-1.xml")
    assert resp.status_code == 200
    entries = _entries(_parse(resp.text))
    locs = list(entries)
    assert any(loc.endswith(f"/items/{scored.slug}") for loc in locs)
    assert not any(loc.endswith(f"/items/{never.slug}") for loc in locs)
    assert not any(loc.endswith(f"/items/{placeholder.slug}") for loc in locs)
    scored_loc = next(loc for loc in locs if loc.endswith(f"/items/{scored.slug}"))
    assert "2026-03-04" in entries[scored_loc]


@pytest.mark.asyncio
async def test_rescan_placeholder_keeps_completed_scan_and_sitemap_agree(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """FIX 1 invariant: an item with an OLDER completed scan + a NEWER `unscoped`
    placeholder (the row a rescan inserts at its start) must (a) return the
    COMPLETED scan as `latest_scan` from `GET /items/{slug}` — so the page renders
    indexable, not noindex/unscored — AND (b) still appear in `items-1.xml`. The
    page predicate (`isIndexableScan(latest_scan)`) and the sitemap predicate
    (`tier != 'unscoped'`) therefore agree."""
    suffix = uuid.uuid4().hex[:8]
    item = _make_item(f"acme--rescanning-{suffix}")
    db_session.add(item)
    await db_session.flush()

    older = datetime(2026, 2, 1, 0, 0, 0, tzinfo=UTC)
    newer = datetime(2026, 2, 2, 0, 0, 0, tzinfo=UTC)
    db_session.add_all(
        [
            _make_scan(item.id, tier="green", scanned_at=older, score=88),
            # The freshly-inserted rescan placeholder (newest, but unscoped).
            _make_scan(item.id, tier="unscoped", scanned_at=newer, score=0),
        ]
    )
    await db_session.flush()

    # (a) the detail endpoint returns the COMPLETED scan, not the placeholder.
    detail = await db_client.get(f"/api/v1/items/{item.slug}")
    assert detail.status_code == 200
    latest_scan = detail.json()["latest_scan"]
    assert latest_scan is not None
    assert latest_scan["tier"] == "green"
    assert latest_scan["aggregate_score"] == 88

    # (b) the item is present in the sitemap items shard (predicates agree).
    shard = await db_client.get("/api/v1/sitemap/shard/items-1.xml")
    locs = list(_entries(_parse(shard.text)))
    assert any(loc.endswith(f"/items/{item.slug}") for loc in locs)


@pytest.mark.asyncio
async def test_agents_shard_graded_only(db_client: AsyncClient, db_session: AsyncSession) -> None:
    graded = _make_agent_run(status="graded", score=72)
    db_session.add_all(
        [
            graded,
            _make_agent_run(status="submitted", score=None),  # ungraded
            _make_agent_run(visibility="unlisted", status="graded", score=72),  # not public
            _make_agent_run(status="graded", score=None),  # graded but no score
        ]
    )
    await db_session.flush()

    resp = await db_client.get("/api/v1/sitemap/shard/agents-1.xml")
    assert resp.status_code == 200
    locs = _loc_texts(_parse(resp.text), ".//sm:url/sm:loc")
    assert any(loc.endswith(f"/agents/{graded.id}") for loc in locs)
    assert not any("/agents/r/" in loc for loc in locs)
    assert len(locs) == 1


@pytest.mark.asyncio
async def test_unknown_section_404s(db_client: AsyncClient, db_session: AsyncSession) -> None:
    resp = await db_client.get("/api/v1/sitemap/shard/bogus-1.xml")
    assert resp.status_code == 404
