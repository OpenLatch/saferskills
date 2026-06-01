"""Tests for GET /api/v1/items (list + pagination + filters) and /items/facets.

Covers the Phase-B catalog-rewrite additions: offset/page pagination, the
`agent` array-overlap filter, the `popularity_tier` filter, and the `agent`
facet distribution. DB-backed — runs in the `test-be` CI lane against Postgres.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.catalog_item import CatalogItem


async def _seed(session: AsyncSession, n: int = 5) -> str:
    """Insert `n` catalog items with a shared random prefix; return the prefix."""
    prefix = uuid.uuid4().hex[:8]
    specs = [
        ("mcp_server", "deep", 90, ["claude-code", "cursor", "codex", "gemini"]),
        ("skill", "lite", 70, ["claude-code", "openclaw"]),
        ("rules", "indexed", 50, ["cursor", "windsurf", "cline", "copilot"]),
        ("plugin", "indexed", 30, ["claude-code", "openclaw"]),
        ("hook", "lite", 10, ["claude-code", "openclaw"]),
    ]
    for i in range(n):
        kind, tier, pop, agents = specs[i % len(specs)]
        item = CatalogItem(
            kind=kind,
            slug=f"{prefix}-org--repo-{i:02d}",
            display_name=f"Item {i}",
            github_url=f"https://github.com/{prefix}/repo-{i:02d}",
            github_org=prefix,
            github_repo=f"repo-{i:02d}",
            default_branch="main",
            popularity_tier=tier,
            popularity_score=pop,
            agent_compatibility=agents,
            sources=[],
        )
        session.add(item)
    await session.flush()
    return prefix


@pytest.mark.asyncio
async def test_list_envelope_has_pagination_fields(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    await _seed(db_session, 3)
    resp = await db_client.get("/api/v1/items", params={"limit": 25})
    assert resp.status_code == 200
    body = resp.json()
    assert "data" in body
    assert body["page"] == 1
    assert body["page_size"] == 25
    assert body["total_pages"] >= 1
    assert isinstance(body["total_count"], int)
    # Wire contract: new field present on every summary row.
    if body["data"]:
        assert "agent_compatibility" in body["data"][0]


@pytest.mark.asyncio
async def test_offset_pagination_pages_differ(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    prefix = await _seed(db_session, 5)
    p1 = (await db_client.get("/api/v1/items", params={"limit": 2, "page": 1})).json()
    p2 = (await db_client.get("/api/v1/items", params={"limit": 2, "page": 2})).json()
    assert p1["page"] == 1
    assert p2["page"] == 2
    assert p1["total_pages"] >= 3
    slugs1 = {r["slug"] for r in p1["data"]}
    slugs2 = {r["slug"] for r in p2["data"]}
    # Pages must not overlap.
    assert slugs1.isdisjoint(slugs2)
    # Both pages should be drawn from the seeded prefix corpus.
    assert all(s.startswith(prefix) for s in slugs1 | slugs2)


@pytest.mark.asyncio
async def test_page_zero_is_rejected(db_client: AsyncClient) -> None:
    resp = await db_client.get("/api/v1/items", params={"page": 0})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_agent_filter_overlap(db_client: AsyncClient, db_session: AsyncSession) -> None:
    prefix = await _seed(db_session, 5)
    resp = await db_client.get("/api/v1/items", params={"agent": ["windsurf"], "limit": 100})
    assert resp.status_code == 200
    rows = [r for r in resp.json()["data"] if r["slug"].startswith(prefix)]
    # Only the `rules` item declares windsurf compatibility.
    assert rows
    assert all("windsurf" in r["agent_compatibility"] for r in rows)


@pytest.mark.asyncio
async def test_unknown_agent_returns_empty_not_error(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    prefix = await _seed(db_session, 5)
    resp = await db_client.get("/api/v1/items", params={"agent": ["not-an-agent"], "limit": 100})
    assert resp.status_code == 200
    rows = [r for r in resp.json()["data"] if r["slug"].startswith(prefix)]
    assert rows == []


@pytest.mark.asyncio
async def test_popularity_tier_filter(db_client: AsyncClient, db_session: AsyncSession) -> None:
    prefix = await _seed(db_session, 5)
    resp = await db_client.get("/api/v1/items", params={"popularity_tier": ["deep"], "limit": 100})
    assert resp.status_code == 200
    rows = [r for r in resp.json()["data"] if r["slug"].startswith(prefix)]
    assert rows
    assert all(r["popularity_tier"] == "deep" for r in rows)


@pytest.mark.asyncio
async def test_facets_include_agent_distribution(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    await _seed(db_session, 5)
    resp = await db_client.get("/api/v1/items/facets")
    assert resp.status_code == 200
    facets = resp.json()
    assert "agent" in facets
    assert isinstance(facets["agent"], dict)
    # claude-code appears in skill/plugin/hook/mcp_server → must be present + > 0.
    assert facets["agent"].get("claude-code", 0) >= 1
