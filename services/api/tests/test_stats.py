"""Tests for the homepage stats surface.

Covers:
- `rule_count()` is the single source of truth = the loaded rubric registry.
- Median / p95 / avg latency math over seeded scans, with pending (`unscoped`)
  rows excluded.
- Catalog total / distinct-registry / tier-distribution helpers.
- The GitHub-stars proxy: cached success (mocked httpx) + `None` on timeout.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app import queries
from app.db.session import get_session
from app.main import app
from app.routers import stats as stats_router
from app.routers.stats import rule_count
from app.scan import rubric
from app.services import github_stars


def test_rule_count_matches_loaded_registry() -> None:
    assert rule_count() == len(rubric.RULES)
    # The rubric ships a non-trivial first batch; guard against a silent empty load.
    assert rule_count() >= 1


async def _seed_item(session: AsyncSession, slug: str) -> str:
    return str(
        (
            await session.execute(
                text(
                    """
                    INSERT INTO catalog_items (
                        kind, slug, display_name, github_org, github_repo,
                        default_branch, popularity_tier, popularity_score, sources
                    ) VALUES (
                        'skill', :slug, :slug, 'org', :slug,
                        'main', 'lite', 10, '[]'::jsonb
                    )
                    RETURNING id
                    """
                ),
                {"slug": slug},
            )
        ).scalar_one()
    )


async def _seed_scan(
    session: AsyncSession,
    *,
    item_id: str,
    idem: str,
    score: int,
    tier: str,
    latency_ms: int,
) -> None:
    await session.execute(
        text(
            """
            INSERT INTO scans (
                catalog_item_id, idempotency_key, github_url, ref_sha,
                aggregate_score, tier, sub_scores, score_breakdown,
                rubric_version, engine_version, latency_ms, source
            ) VALUES (
                :item_id, :idem, 'https://github.com/org/x', :sha,
                :score, :tier, '{}'::jsonb, '{}'::jsonb,
                'a1b2c3d', 'def5678', :latency, 'submission'
            )
            """
        ),
        {
            "item_id": item_id,
            "idem": idem,
            "sha": "f" * 40,
            "score": score,
            "tier": tier,
            "latency": latency_ms,
        },
    )


async def _seed_run(
    session: AsyncSession,
    *,
    idem: str,
    score: int,
    tier: str,
    latency_ms: int,
    status: str,
) -> None:
    await session.execute(
        text(
            """
            INSERT INTO scan_runs (
                idempotency_key, github_url, repo_aggregate_score, repo_tier,
                rubric_version, engine_version, source, latency_ms, status
            ) VALUES (
                :idem, 'https://github.com/org/x', :score, :tier,
                'a1b2c3d', 'def5678', 'submission', :latency, :status
            )
            """
        ),
        {"idem": idem, "score": score, "tier": tier, "latency": latency_ms, "status": status},
    )


@pytest.mark.asyncio
async def test_median_and_latency_exclude_pending(db_session: AsyncSession) -> None:
    item_id = await _seed_item(db_session, "stats-median")
    # Median is over per-capability scans (tier != unscoped); the pending
    # (unscoped) scan must be excluded.
    await _seed_scan(
        db_session, item_id=item_id, idem="a" * 64, score=40, tier="orange", latency_ms=0
    )
    await _seed_scan(
        db_session, item_id=item_id, idem="b" * 64, score=60, tier="yellow", latency_ms=0
    )
    await _seed_scan(
        db_session, item_id=item_id, idem="c" * 64, score=80, tier="green", latency_ms=0
    )
    await _seed_scan(
        db_session, item_id=item_id, idem="d" * 64, score=0, tier="unscoped", latency_ms=0
    )
    # Latency is over completed repo SCAN RUNS (the timed unit); the pending run
    # must be excluded (per-capability scans carry latency_ms=0).
    await _seed_run(
        db_session, idem="r" * 64, score=40, tier="orange", latency_ms=10_000, status="completed"
    )
    await _seed_run(
        db_session, idem="s" * 64, score=60, tier="yellow", latency_ms=20_000, status="completed"
    )
    await _seed_run(
        db_session, idem="t" * 64, score=80, tier="green", latency_ms=30_000, status="completed"
    )
    await _seed_run(
        db_session, idem="u" * 64, score=0, tier="unscoped", latency_ms=0, status="pending"
    )
    await db_session.flush()

    assert await queries.median_completed_score(db_session) == 60
    p95, avg = await queries.latency_stats_ms(db_session)
    assert avg == 20_000
    # percentile_cont(0.95) over [10k,20k,30k] = 20k + 0.9*(30k-20k) = 29k.
    assert p95 == 29_000


@pytest.mark.asyncio
async def test_median_none_when_no_completed(db_session: AsyncSession) -> None:
    item_id = await _seed_item(db_session, "stats-empty")
    await _seed_scan(
        db_session, item_id=item_id, idem="e" * 64, score=0, tier="unscoped", latency_ms=0
    )
    await db_session.flush()
    assert await queries.median_completed_score(db_session) is None
    assert await queries.latency_stats_ms(db_session) == (None, None)


@pytest.mark.asyncio
async def test_catalog_total_and_registries(db_session: AsyncSession) -> None:
    item_id = await _seed_item(db_session, "stats-reg")
    await db_session.execute(
        text(
            """
            INSERT INTO item_sources (catalog_item_id, registry_id, registry_url)
            VALUES (:id, 'mcp_registry', 'https://e/1'), (:id, 'npm', 'https://e/2')
            """
        ),
        {"id": item_id},
    )
    await db_session.flush()
    assert await queries.count_catalog_total(db_session) >= 1
    assert await queries.count_distinct_registries(db_session) >= 2


@pytest.mark.asyncio
async def test_tier_distribution_uses_latest_scan(db_session: AsyncSession) -> None:
    item_id = await _seed_item(db_session, "stats-tier")
    await _seed_scan(
        db_session, item_id=item_id, idem="f" * 64, score=90, tier="green", latency_ms=5_000
    )
    await db_session.flush()
    dist = await queries.latest_scan_tier_distribution(db_session)
    assert dist.get("green", 0) >= 1


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict[str, Any]) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self) -> dict[str, Any]:
        return self._payload


class _FakeClient:
    def __init__(self, *, response: _FakeResponse | None, exc: Exception | None) -> None:
        self._response = response
        self._exc = exc

    async def __aenter__(self) -> _FakeClient:
        return self

    async def __aexit__(self, *_: object) -> None:
        return None

    async def get(self, *_: object, **__: object) -> _FakeResponse:
        if self._exc is not None:
            raise self._exc
        assert self._response is not None
        return self._response


@pytest.mark.asyncio
async def test_github_stars_success_and_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    github_stars.reset_cache()
    calls = {"n": 0}

    def _factory(*_: object, **__: object) -> _FakeClient:
        calls["n"] += 1
        return _FakeClient(response=_FakeResponse(200, {"stargazers_count": 1234}), exc=None)

    monkeypatch.setattr(github_stars.httpx, "AsyncClient", _factory)
    assert await github_stars.get_github_stars() == 1234
    # Second call is served from the in-process cache — no new HTTP client.
    assert await github_stars.get_github_stars() == 1234
    assert calls["n"] == 1
    github_stars.reset_cache()


@pytest.mark.asyncio
async def test_github_stars_timeout_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    github_stars.reset_cache()

    def _factory(*_: object, **__: object) -> _FakeClient:
        return _FakeClient(response=None, exc=httpx.ConnectTimeout("timed out"))

    monkeypatch.setattr(github_stars.httpx, "AsyncClient", _factory)
    assert await github_stars.get_github_stars() is None
    github_stars.reset_cache()


@pytest.mark.asyncio
async def test_stats_endpoint_shape_and_cache_header(
    client: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Route the endpoint at the rolled-back test session; stub the network proxy.
    async def _override() -> AsyncIterator[AsyncSession]:
        yield db_session

    async def _fake_stars() -> int | None:
        return 4321

    stats_router.reset_cache()
    app.dependency_overrides[get_session] = _override
    monkeypatch.setattr(stats_router, "get_github_stars", _fake_stars)
    try:
        resp = await client.get("/api/v1/stats")
    finally:
        app.dependency_overrides.pop(get_session, None)
        stats_router.reset_cache()

    assert resp.status_code == 200
    assert resp.headers["cache-control"] == "public, s-maxage=60, stale-while-revalidate=300"
    body = resp.json()
    assert body["rule_count"] == len(rubric.RULES)
    assert body["agents_count"] == 8
    assert body["github_stars"] == 4321
    # snake_case keys per OrmBaseModel contract.
    assert "tier_distribution" in body and "p95_latency_ms" in body
