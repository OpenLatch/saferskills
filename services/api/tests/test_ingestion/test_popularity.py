"""Popularity formula (pure) + recompute_all/recompute_one (DB) — D-04-13."""
# pyright: reportPrivateUsage=false

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.ingestion.popularity import PopularityWeights, _normalize_log, compute_popularity_score
from app.ingestion.tasks_popularity import recompute_all, recompute_one

from ._catalog_factory import make_item

_W = PopularityWeights(
    stars=0.45, velocity=0.20, downloads=0.20, cross_registry=0.10, recency=0.05, version="v1"
)


def test_normalize_log_bounds() -> None:
    assert _normalize_log(0, 100) == 0.0
    assert _normalize_log(50, 0) == 0.0
    assert _normalize_log(100, 100) == 1.0  # log(101)/log(101) is exactly 1.0
    assert 0.0 < _normalize_log(10, 100) < 1.0


def test_compute_score_is_deterministic_and_bounded() -> None:
    score, breakdown = compute_popularity_score(
        weights=_W,
        stars=100,
        star_velocity_7d=5.0,
        weekly_downloads=1000,
        cross_registry_count=2,
        days_since_pushed=30,
        max_stars=100,
        max_velocity=5.0,
        max_downloads=1000,
    )
    score2, _ = compute_popularity_score(
        weights=_W,
        stars=100,
        star_velocity_7d=5.0,
        weekly_downloads=1000,
        cross_registry_count=2,
        days_since_pushed=30,
        max_stars=100,
        max_velocity=5.0,
        max_downloads=1000,
    )
    assert score == score2
    assert 0.0 <= score <= 1.0
    assert breakdown["formulaVersion"] == "v1"
    assert set(breakdown) >= {"starsTerm", "velocityTerm", "downloadsTerm", "recencyTerm"}


def test_more_stars_scores_higher() -> None:
    def score_for(stars: int) -> float:
        s, _ = compute_popularity_score(
            weights=_W,
            stars=stars,
            star_velocity_7d=0.0,
            weekly_downloads=0,
            cross_registry_count=0,
            days_since_pushed=None,
            max_stars=1000,
            max_velocity=1.0,
            max_downloads=1,
        )
        return s

    assert score_for(900) > score_for(10)


@pytest.mark.asyncio
async def test_recompute_all_assigns_score_and_top500(db_session: AsyncSession) -> None:
    popular = make_item(item_metadata={"stars": 5000})
    niche = make_item(item_metadata={"stars": 1})
    db_session.add_all([popular, niche])
    await db_session.commit()

    result = await recompute_all(db_session)
    assert result["total_updated"] >= 2

    await db_session.refresh(popular)
    await db_session.refresh(niche)
    assert popular.popularity_score >= niche.popularity_score
    assert popular.popularity_rank_tier == "top500"
    # formulaVersion mirrors the active popularity_formulas row (seeded 'popularity_v1').
    assert popular.popularity_breakdown.get("formulaVersion")


@pytest.mark.asyncio
async def test_recompute_one_updates_single_row(db_session: AsyncSession) -> None:
    item = make_item(item_metadata={"stars": 42})
    db_session.add(item)
    await db_session.commit()

    out = await recompute_one(db_session, str(item.id))
    assert out == {"updated": 1}


@pytest.mark.asyncio
async def test_recompute_one_skips_unlisted(db_session: AsyncSession) -> None:
    item = make_item(visibility="unlisted", item_metadata={"stars": 99})
    db_session.add(item)
    await db_session.commit()
    out = await recompute_one(db_session, str(item.id))
    assert out == {"updated": 0}
