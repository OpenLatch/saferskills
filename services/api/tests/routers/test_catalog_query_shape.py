"""Catalog reads must not touch `scans`.

Recomputing "latest scan" over all of `scans` per request is what overloaded
production. These assert on the SQL each read runs, not on plans, which are unstable
on small test tables.
"""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.catalog_item import CatalogItem
from app.models.scan import Scan
from app.queries import latest_scan_tier_distribution, median_completed_score
from app.routers.items import _related_items  # pyright: ignore[reportPrivateUsage]
from app.scan.persistence import refresh_latest_scan
from tests.sql_capture import capture_sql

_READS_SCANS = re.compile(r"\bscans\b", re.IGNORECASE)


async def _seed(session: AsyncSession) -> CatalogItem:
    token = uuid.uuid4().hex[:8]
    item = CatalogItem(
        kind="skill",
        slug=f"{token}--shape",
        display_name=token,
        github_url=f"https://github.com/{token}/shape",
        github_org=token,
        github_repo="shape",
        default_branch="main",
        popularity_tier="indexed",
        popularity_score=5,
        agent_compatibility=[],
        sources=[],
    )
    session.add(item)
    await session.flush()
    session.add(
        Scan(
            catalog_item_id=item.id,
            idempotency_key=uuid.uuid4().hex,
            github_url=item.github_url,
            ref_sha="0" * 40,
            aggregate_score=81,
            tier="green",
            sub_scores={},
            score_breakdown={},
            rubric_version="r",
            engine_version="e",
            latency_ms=0,
            source="submission",
            scanned_at=datetime(2026, 1, 2, tzinfo=UTC),
        )
    )
    await refresh_latest_scan(session, [item.id])
    return item


def _assert_no_scan_reads(statements: list[str]) -> None:
    assert statements
    offending = [s for s in statements if _READS_SCANS.search(s) or "row_number" in s]
    assert not offending, offending


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "params",
    [
        {},
        {"sort": "highest_score"},
        {"sort": "lowest_score"},
        {"sort": "most_active"},
        {"scan_tier": "green"},
        {"score_min": "50"},
        {"q": "shape"},
    ],
)
async def test_list_items_never_reads_scans(
    db_client: AsyncClient, db_session: AsyncSession, params: dict[str, str]
) -> None:
    await _seed(db_session)

    async with capture_sql(db_session) as statements:
        resp = await db_client.get("/api/v1/items", params=params)

    assert resp.status_code == 200
    _assert_no_scan_reads(statements)


@pytest.mark.asyncio
async def test_list_items_uses_the_partial_index_predicate(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """`archived IS false` silently loses the partial index; see `queries.LISTED_ITEM`."""
    await _seed(db_session)

    async with capture_sql(db_session) as statements:
        resp = await db_client.get("/api/v1/items", params={"sort": "highest_score"})

    assert resp.status_code == 200
    listing = next(s for s in statements if "ORDER BY" in s and "catalog_items" in s)
    assert "archived = false" in listing
    assert "visibility = 'public'" in listing
    assert "IS false" not in listing


@pytest.mark.asyncio
async def test_list_items_projects_scan_fields_and_page_findings(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    item = await _seed(db_session)

    resp = await db_client.get("/api/v1/items", params={"q": item.display_name})

    row = next(r for r in resp.json()["data"] if r["slug"] == item.slug)
    assert row["latest_scan_score"] == 81
    assert row["latest_scan_tier"] == "green"
    assert row["latest_scan_at"].startswith("2026-01-02")
    assert row["findings_count"] == 0


@pytest.mark.asyncio
async def test_stats_aggregates_never_read_scans(db_session: AsyncSession) -> None:
    await _seed(db_session)

    async with capture_sql(db_session) as statements:
        tiers = await latest_scan_tier_distribution(db_session)
        median = await median_completed_score(db_session)

    assert tiers.get("green", 0) >= 1
    assert median is not None
    _assert_no_scan_reads(statements)


@pytest.mark.asyncio
async def test_facets_never_read_scans(db_client: AsyncClient, db_session: AsyncSession) -> None:
    await _seed(db_session)

    async with capture_sql(db_session) as statements:
        resp = await db_client.get("/api/v1/items/facets")

    assert resp.status_code == 200
    _assert_no_scan_reads(statements)


@pytest.mark.asyncio
async def test_sitemap_never_reads_scans(db_client: AsyncClient, db_session: AsyncSession) -> None:
    item = await _seed(db_session)

    async with capture_sql(db_session) as statements:
        index = await db_client.get("/api/v1/sitemap/index.xml")
        shard = await db_client.get("/api/v1/sitemap/shard/items-1.xml")

    assert index.status_code == 200
    assert f"/items/{item.slug}<" in shard.text
    _assert_no_scan_reads(statements)
    assert any("LIMIT" in s for s in statements), "a shard must read only its window"


@pytest.mark.asyncio
async def test_related_items_never_read_scans(db_session: AsyncSession) -> None:
    item = await _seed(db_session)
    peer = await _seed(db_session)

    async with capture_sql(db_session) as statements:
        related = await _related_items(db_session, kind="skill", exclude_id=item.id, limit=50)

    assert peer.slug in {r.slug for r in related}
    _assert_no_scan_reads(statements)
