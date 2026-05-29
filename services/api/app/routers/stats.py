"""Homepage platform-metrics surface — `GET /api/v1/stats`.

Single endpoint backing every live homepage metric (catalog size, registries,
tier mix, median score, scan latency, rule count, agents, GitHub stars). The
whole payload is memoized in-process for ~60s (no Redis per
`.claude/rules/tech-stack.md`); `github_stars` carries its own ~1h cache inside
`services.github_stars`.

Every scalar is nullable / floored so the frontend's `pickCount` fallback can
decide whether the live value is impressive enough to show or whether the
launch placeholder should stand in (see `.claude/rules/frontend-patterns.md`).
"""

from __future__ import annotations

import time

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.queries import (
    count_catalog_total,
    count_distinct_registries,
    latency_stats_ms,
    latest_scan_tier_distribution,
    median_completed_score,
)
from app.scan import rubric
from app.schemas.stats import PlatformStats
from app.services.github_stars import get_github_stars

router = APIRouter(prefix="/stats", tags=["stats"])

# Mirrors the frontend's `SUPPORTED_AGENTS` config length — echoed for symmetry
# so the homepage "N agents" stat has a single live source. Update both when a
# platform is added.
SUPPORTED_AGENTS_COUNT = 8

_CACHE_TTL_SECONDS = 60.0
_cache: tuple[float, PlatformStats] | None = None


def rule_count() -> int:
    """Active rubric rule count the scan engine loads — the SSOT the methodology
    generator also walks (kills the 87↔55↔57 drift)."""
    return len(rubric.RULES)


async def _compute(session: AsyncSession) -> PlatformStats:
    catalog_total = await count_catalog_total(session)
    registries_count = await count_distinct_registries(session)
    tier_distribution = await latest_scan_tier_distribution(session)
    median_score = await median_completed_score(session)
    p95_latency_ms, avg_latency_ms = await latency_stats_ms(session)
    github_stars = await get_github_stars()

    return PlatformStats(
        catalog_total=catalog_total,
        registries_count=registries_count,
        tier_distribution=tier_distribution,
        median_score=median_score,
        p95_latency_ms=p95_latency_ms,
        avg_latency_ms=avg_latency_ms,
        rule_count=rule_count(),
        agents_count=SUPPORTED_AGENTS_COUNT,
        github_stars=github_stars,
    )


@router.get("", response_model=PlatformStats, summary="Homepage platform metrics.")
async def get_stats(
    response: Response,
    session: AsyncSession = Depends(get_session),
) -> PlatformStats:
    global _cache
    response.headers["Cache-Control"] = "public, s-maxage=60, stale-while-revalidate=300"

    now = time.monotonic()
    if _cache is not None and (now - _cache[0]) < _CACHE_TTL_SECONDS:
        return _cache[1]

    stats = await _compute(session)
    _cache = (now, stats)
    return stats


def reset_cache() -> None:
    """Clear the memoized payload. Used by tests; harmless in production."""
    global _cache
    _cache = None
