"""Hand-written `PlatformStats` response model for `GET /api/v1/stats`.

One payload backing every homepage metric. Snake_case keys (inherits
`OrmBaseModel`); the TS DTO falls out of `openapi.json` via the codegen
pipeline. Scalar metrics are nullable so the route can report "no data yet"
and let the frontend fall back to its launch placeholder.
"""

from __future__ import annotations

from pydantic import Field

from app.schemas.orm_base import OrmBaseModel


class PlatformStats(OrmBaseModel):
    catalog_total: int = Field(..., ge=0, description="Non-archived catalog item count.")
    registries_count: int = Field(..., ge=0, description="Distinct registries sourced from.")
    tier_distribution: dict[str, int] = Field(
        default_factory=dict, description="Item count bucketed by latest-scan tier."
    )
    median_score: int | None = Field(
        default=None, ge=0, le=100, description="P50 aggregate score over completed scans."
    )
    p95_latency_ms: int | None = Field(
        default=None, ge=0, description="P95 scan latency in ms over completed scans."
    )
    avg_latency_ms: int | None = Field(
        default=None, ge=0, description="Average scan latency in ms over completed scans."
    )
    rule_count: int = Field(..., ge=0, description="Active rubric rule count the engine loads.")
    agents_count: int = Field(..., ge=0, description="Supported agent platforms (static config).")
    github_stars: int | None = Field(
        default=None, ge=0, description="Repo star count (cached proxy); null when unavailable."
    )
