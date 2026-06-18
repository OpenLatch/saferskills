"""Weighted popularity formula v1.

Pure functions only — no DB writes here. The active weights live in the
`popularity_formulas` table (seeded `popularity_formula_v1` in migration 0011);
`get_active_weights` reads the row flagged `active = true`. The periodic task
(`tasks_popularity.popularity_recompute`) calls `compute_popularity_score` per
public-github capability row and persists the result.

Score is in [0, 1]; the caller scales to the 0-100 integer `catalog_items.popularity_score`
and stores the per-term float breakdown in `catalog_items.popularity_breakdown`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True)
class PopularityWeights:
    stars: float
    velocity: float
    downloads: float
    cross_registry: float
    recency: float
    version: str


async def get_active_weights(session: AsyncSession) -> PopularityWeights:
    """Read the active formula weights from `popularity_formulas`."""
    row = (
        await session.execute(
            text("SELECT version, weights FROM popularity_formulas WHERE active = true LIMIT 1")
        )
    ).one()
    w = row.weights
    return PopularityWeights(
        stars=float(w["starsTerm"]),
        velocity=float(w["velocityTerm"]),
        downloads=float(w["downloadsTerm"]),
        cross_registry=float(w["crossRegistryTerm"]),
        recency=float(w["recencyTerm"]),
        version=row.version,
    )


def _normalize_log(x: float, max_value: float) -> float:
    """Log-normalize x into [0, 1] against the nightly-recomputed max."""
    if max_value <= 0 or x <= 0:
        return 0.0
    return math.log(x + 1) / math.log(max_value + 1)


def compute_popularity_score(
    *,
    weights: PopularityWeights,
    stars: int,
    star_velocity_7d: float,
    weekly_downloads: int,
    cross_registry_count: int,
    days_since_pushed: int | None,
    max_stars: int,
    max_velocity: float,
    max_downloads: int,
) -> tuple[float, dict[str, float | str]]:
    """Return (score in [0,1], per-term breakdown). Weights sum to 1.0 in v1."""
    stars_term = _normalize_log(stars, max_stars)
    velocity_term = _normalize_log(star_velocity_7d, max_velocity)
    downloads_term = _normalize_log(weekly_downloads, max_downloads)
    cross_registry_term = min(1.0, cross_registry_count / 14.0)
    recency_term = max(
        0.0, 1.0 - (days_since_pushed if days_since_pushed is not None else 365) / 365.0
    )

    score = (
        weights.stars * stars_term
        + weights.velocity * velocity_term
        + weights.downloads * downloads_term
        + weights.cross_registry * cross_registry_term
        + weights.recency * recency_term
    )
    breakdown: dict[str, float | str] = {
        "starsTerm": round(stars_term, 6),
        "velocityTerm": round(velocity_term, 6),
        "downloadsTerm": round(downloads_term, 6),
        "crossRegistryTerm": round(cross_registry_term, 6),
        "recencyTerm": round(recency_term, 6),
        "formulaVersion": weights.version,
    }
    return score, breakdown
