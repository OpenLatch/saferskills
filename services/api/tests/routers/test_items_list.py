"""Tests for GET /api/v1/items (list + pagination + filters) and /items/facets.

Covers the Phase-B catalog-rewrite additions: offset/page pagination, the
`agent` array-overlap filter, the `popularity_tier` filter, and the `agent`
facet distribution. DB-backed — runs in the `test-be` CI lane against Postgres.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.catalog_item import CatalogItem
from app.models.install_event import InstallEvent
from app.models.scan import Scan


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
async def test_artifact_source_filter_and_summary_field(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """I-3.5: catalog rows carry `source_kind`; `?artifact_source=upload` narrows
    to uploads; the facet splits github|upload."""
    prefix = uuid.uuid4().hex[:8]
    db_session.add(
        CatalogItem(
            kind="skill",
            slug=f"upload--{prefix}--skill-up",
            # Prefix lives in display_name so the FTS `q` search (D-04-32 — searches
            # display_name/org/repo/description, NOT slug) isolates this row. An
            # upload has no github coords, so display_name is the only searchable field.
            display_name=f"Uploaded {prefix}",
            github_url=None,
            github_org=None,
            github_repo=None,
            default_branch=None,
            popularity_tier="on_demand",
            popularity_score=42,
            agent_compatibility=["claude-code"],
            source_kind="upload",
            visibility="public",
            sources=[{"registryId": "upload"}],
        )
    )
    db_session.add(
        CatalogItem(
            kind="skill",
            slug=f"{prefix}-org--repo-gh",
            display_name="GitHub one",
            github_url=f"https://github.com/{prefix}/repo-gh",
            github_org=prefix,
            github_repo="repo-gh",
            default_branch="main",
            popularity_tier="lite",
            popularity_score=50,
            agent_compatibility=["claude-code"],
            source_kind="github",
            sources=[],
        )
    )
    await db_session.flush()

    only_upload = (
        await db_client.get("/api/v1/items", params={"q": prefix, "artifact_source": "upload"})
    ).json()
    slugs = {row["slug"] for row in only_upload["data"]}
    assert any(s.startswith("upload--") for s in slugs)
    assert all(row["source_kind"] == "upload" for row in only_upload["data"])

    facets = (await db_client.get("/api/v1/items/facets")).json()
    assert "artifact_source" in facets
    assert facets["artifact_source"].get("upload", 0) >= 1


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


async def _seed_scored(session: AsyncSession, scores: list[int]) -> str:
    """Seed items whose display_name shares a unique search token, each with one
    Scan carrying a distinct aggregate_score. Returns the shared search token."""
    token = f"qsort{uuid.uuid4().hex[:8]}"
    now = datetime.now(tz=UTC)
    for i, score in enumerate(scores):
        item = CatalogItem(
            kind="mcp_server",
            slug=f"{token}-org--repo-{i:02d}",
            # token lives in display_name so the FTS `q` search isolates these rows.
            display_name=f"{token} item {i}",
            github_url=f"https://github.com/{token}/repo-{i:02d}",
            github_org=token,
            github_repo=f"repo-{i:02d}",
            default_branch="main",
            popularity_tier="deep",
            # Distinct, descending popularity so the relevance/default order is
            # provably different from the score order (proves the sort override).
            popularity_score=100 - i,
            agent_compatibility=["claude-code"],
            sources=[],
        )
        session.add(item)
        await session.flush()
        session.add(
            Scan(
                catalog_item_id=item.id,
                idempotency_key=uuid.uuid4().hex,
                github_url=item.github_url,
                ref_sha=f"{i:040d}",
                aggregate_score=score,
                tier="green" if score >= 80 else "yellow" if score >= 60 else "orange",
                sub_scores={
                    "security": score,
                    "supply_chain": score,
                    "maintenance": score,
                    "transparency": score,
                    "community": score,
                },
                score_breakdown={},
                rubric_version="abc1234",
                engine_version="def5678",
                latency_ms=100,
                source="submission",
                scanned_at=now,
            )
        )
    await session.flush()
    return token


@pytest.mark.asyncio
async def test_explicit_sort_overrides_relevance_when_searching(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Regression (catalog redesign): an explicit Score sort must be honored even
    while a search query `q` is active. Previously any `q` forced relevance
    ordering and silently ignored `sort`, so clicking the Score header changed the
    URL but never reordered the search results."""
    token = await _seed_scored(db_session, [30, 90, 60])

    asc = (
        await db_client.get(
            "/api/v1/items", params={"q": token, "sort": "lowest_score", "limit": 50}
        )
    ).json()
    asc_scores = [r["latest_scan_score"] for r in asc["data"] if r["slug"].startswith(token)]
    assert asc_scores == [30, 60, 90], asc_scores

    desc = (
        await db_client.get(
            "/api/v1/items", params={"q": token, "sort": "highest_score", "limit": 50}
        )
    ).json()
    desc_scores = [r["latest_scan_score"] for r in desc["data"] if r["slug"].startswith(token)]
    assert desc_scores == [90, 60, 30], desc_scores


@pytest.mark.asyncio
async def test_search_default_sort_stays_relevance(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """The default (Trend / most_installed) order while searching stays the
    relevance blend (ts_rank + popularity), NOT score — so the D-04-32 search
    default is preserved, only explicit sorts override it."""
    # Scores ascend with index (30,60,90) but popularity descends (100,99,98),
    # so a relevance/popularity order is the reverse of a score order.
    token = await _seed_scored(db_session, [30, 60, 90])
    body = (
        await db_client.get(
            "/api/v1/items", params={"q": token, "sort": "most_installed", "limit": 50}
        )
    ).json()
    scores = [r["latest_scan_score"] for r in body["data"] if r["slug"].startswith(token)]
    # Popularity-weighted relevance → first row is the high-popularity (low-score)
    # item, i.e. NOT ascending-by-score and NOT descending-by-score.
    assert scores[0] == 30, scores


@pytest.mark.asyncio
async def test_name_sort_orders_alphabetically(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Capability column: name_asc / name_desc order by display_name."""
    token = uuid.uuid4().hex[:8]
    for label in ("Charlie", "alpha", "Bravo"):
        db_session.add(
            CatalogItem(
                kind="skill",
                slug=f"{token}-{label.lower()}--repo",
                display_name=f"{label} {token}",
                github_url=f"https://github.com/{token}/{label.lower()}",
                github_org=token,
                github_repo=label.lower(),
                default_branch="main",
                popularity_tier="lite",
                popularity_score=10,
                agent_compatibility=["claude-code"],
                sources=[],
            )
        )
    await db_session.flush()

    asc = (
        await db_client.get("/api/v1/items", params={"q": token, "sort": "name_asc", "limit": 50})
    ).json()
    asc_names = [r["display_name"].split()[0] for r in asc["data"] if r["github_org"] == token]
    # case-insensitive ascending: alpha, Bravo, Charlie
    assert asc_names == ["alpha", "Bravo", "Charlie"], asc_names

    desc = (
        await db_client.get("/api/v1/items", params={"q": token, "sort": "name_desc", "limit": 50})
    ).json()
    desc_names = [r["display_name"].split()[0] for r in desc["data"] if r["github_org"] == token]
    assert desc_names == ["Charlie", "Bravo", "alpha"], desc_names


@pytest.mark.asyncio
async def test_least_installed_orders_by_popularity_asc(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Trend column reversed: least_installed orders by popularity ascending."""
    token = await _seed_scored(db_session, [50, 50, 50])  # popularity = 100, 99, 98
    body = (
        await db_client.get(
            "/api/v1/items", params={"q": token, "sort": "least_installed", "limit": 50}
        )
    ).json()
    pops = [r["popularity_score"] for r in body["data"] if r["slug"].startswith(token)]
    assert pops == [98, 99, 100], pops


@pytest.mark.asyncio
async def test_activity_sort_and_sparkline(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Activity column: most_active orders by trailing-quarter install count, and
    each row carries a 13-bucket install_sparkline reflecting real installs."""
    token = await _seed_scored(db_session, [50, 50, 50])
    # Fetch the seeded items to attach install events.
    listing = (
        await db_client.get("/api/v1/items", params={"q": token, "sort": "name_asc", "limit": 50})
    ).json()
    seeded = [r for r in listing["data"] if r["slug"].startswith(token)]
    assert len(seeded) == 3
    # Give the middle item (index 1) 3 recent installs, the last item 1.
    now = datetime.now(tz=UTC)
    for item, count in ((seeded[1], 3), (seeded[2], 1)):
        for _ in range(count):
            db_session.add(
                InstallEvent(
                    catalog_item_id=item["id"],
                    agent="claude-code",
                    kind="mcp_server",
                    created_at=now,
                )
            )
    await db_session.flush()

    body = (
        await db_client.get(
            "/api/v1/items", params={"q": token, "sort": "most_active", "limit": 50}
        )
    ).json()
    active = [r for r in body["data"] if r["slug"].startswith(token)]
    # Most installs first: item[1] (3) → item[2] (1) → item[0] (0).
    assert active[0]["id"] == seeded[1]["id"], [r["slug"] for r in active]
    assert active[1]["id"] == seeded[2]["id"]
    # Sparkline is present, length 13, and the busiest item's most-recent bucket
    # carries its install count.
    busiest = active[0]["install_sparkline"]
    assert len(busiest) == 13
    assert sum(busiest) == 3
    assert busiest[-1] == 3  # `now` lands in the newest weekly bucket
