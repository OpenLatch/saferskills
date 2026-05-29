"""Tests for the extended GET /api/v1/items/<slug> item-detail response.

DB-backed — runs in the `test-be` CI lane against Postgres.
"""

from __future__ import annotations

from datetime import UTC

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.catalog_item import CatalogItem
from app.models.scan import Scan

SeededItem = tuple[CatalogItem, Scan]


@pytest.mark.asyncio
async def test_item_detail_unknown_slug_404(db_client: AsyncClient) -> None:
    resp = await db_client.get("/api/v1/items/nope--missing")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_item_detail_shape(db_client: AsyncClient, seed_item: SeededItem) -> None:
    item, _scan = seed_item
    resp = await db_client.get(f"/api/v1/items/{item.slug}")
    assert resp.status_code == 200
    body = resp.json()

    # Nested catalog item
    assert body["item"]["slug"] == item.slug
    assert body["item"]["display_name"] == "Acme Widget"

    # Full latest scan report projected via the shared builder
    assert body["latest_scan"]["aggregate_score"] == 87
    assert body["latest_scan"]["tier"] == "green"
    assert body["latest_scan"]["status"] == "completed"
    assert len(body["latest_scan"]["findings"]) == 1
    assert body["latest_scan"]["findings"][0]["rule_id"] == "SS-MCP-POISON-UNICODE-TAG-01"

    # 90-day history includes the seeded scan
    assert len(body["scan_history"]) == 1
    assert body["scan_history"][0]["aggregate_score"] == 87

    # Anonymized install activity — deterministic + agent distribution sums to 100
    activity = body["install_activity"]
    assert activity["all_time"] >= activity["this_month"] >= activity["this_week"]
    assert sum(a["percentage"] for a in activity["agent_distribution"]) == 100
    # No company-level keys leak into the public payload
    assert "company" not in str(activity).lower()

    # related_items excludes self
    assert all(r["slug"] != item.slug for r in body["related_items"])

    # vendor_responses present (empty until a vendor submits one)
    assert body["vendor_responses"] == []


@pytest.mark.asyncio
async def test_item_detail_related_items_same_kind(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    import uuid
    from datetime import datetime

    suffix = uuid.uuid4().hex[:6]
    base = CatalogItem(
        kind="hook",
        slug=f"base--{suffix}",
        display_name="Base Hook",
        github_url="https://github.com/base/hook",
        github_org="base",
        github_repo="hook",
        default_branch="main",
        popularity_tier="indexed",
        popularity_score=10,
        sources=[],
    )
    peer = CatalogItem(
        kind="hook",
        slug=f"peer--{suffix}",
        display_name="Peer Hook",
        github_url="https://github.com/peer/hook",
        github_org="peer",
        github_repo="hook",
        default_branch="main",
        popularity_tier="indexed",
        popularity_score=5,
        sources=[],
    )
    db_session.add_all([base, peer])
    await db_session.flush()
    db_session.add(
        Scan(
            catalog_item_id=peer.id,
            idempotency_key=uuid.uuid4().hex,
            github_url=peer.github_url,
            ref_sha="b" * 40,
            aggregate_score=73,
            tier="yellow",
            sub_scores={
                "security": 70,
                "supply_chain": 70,
                "maintenance": 70,
                "transparency": 70,
                "community": 70,
            },
            score_breakdown={},
            rubric_version="abc1234",
            engine_version="def5678",
            latency_ms=100,
            source="submission",
            scanned_at=datetime.now(tz=UTC),
        )
    )
    await db_session.flush()

    resp = await db_client.get(f"/api/v1/items/{base.slug}")
    assert resp.status_code == 200
    related = resp.json()["related_items"]
    related_slugs = {r["slug"] for r in related}
    assert peer.slug in related_slugs
    assert base.slug not in related_slugs
