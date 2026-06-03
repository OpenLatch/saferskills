"""Load + validate per-provider YAML configs into `SourceConfig` objects.

The YAML files under `sources/*.yaml` are the single source of truth for a
provider's declarative knobs: which hosts it may fetch, its cadence, its rate
limit, its queue, and a free-form `discovery` block the provider's adapter
interprets. The closed enum of `source` names lives in the JSON Schemas + the
migration CHECK; this loader cross-checks each YAML `name` against that set so a
typo fails fast at import time rather than at insert time.
"""

from __future__ import annotations

import functools
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator

# The crawled adapter sources are generated from `sources/*.yaml` by
# `scripts/generate-ingestion-sources.cjs` (the YAML directory is the single
# source of truth). Re-exported here so existing importers keep working.
# user_submission/upload/vendor_verified are NOT crawled adapters (they are
# endpoints / attributions) and live in the catalog-item schema's fixed set.
from app.ingestion.config.generated.source_registry import SOURCE_NAMES

__all__ = [
    "SOURCE_NAMES",
    "SourceConfig",
    "SourcePolicy",
    "get_source_config",
    "load_source_configs",
]

_CONFIG_DIR = Path(__file__).resolve().parent / "sources"


class SourcePolicy(BaseModel):
    """Public-facing policy excerpt (rendered on the /sources page in Phase C)."""

    model_config = {"extra": "forbid"}

    summary: str = ""
    contact: str = "bot@saferskills.ai"
    robots_txt: str = "n/a"


class SourceConfig(BaseModel):
    """One provider's declarative configuration (validated from YAML)."""

    model_config = {"extra": "forbid"}

    name: str = Field(description="Source name — must be in SOURCE_NAMES.")
    kind: Literal["api", "scrape", "webhook"]
    hosts: list[str] = Field(min_length=1, description="Allowlisted hosts this adapter may fetch.")
    cadence_cron: str | None = Field(
        default=None, description="Cron expression for the periodic task (None = webhook-only)."
    )
    rate_limit_per_second: float = Field(default=0.1, gt=0)
    queue: str = Field(default="default")
    enabled: bool = Field(default=True)
    registry_id: str | None = Field(
        default=None,
        description="Source-of-record id written to item_sources.registry_id (defaults to `name`).",
    )
    discovery: dict[str, Any] = Field(
        default_factory=dict,
        description="Provider-specific discovery params (topics, feed_url, api_base, …).",
    )
    description: str = ""
    policy: SourcePolicy = Field(default_factory=SourcePolicy)

    @field_validator("name")
    @classmethod
    def _known_source(cls, v: str) -> str:
        if v not in SOURCE_NAMES:
            msg = f"Unknown source name '{v}'. Known: {sorted(SOURCE_NAMES)}"
            raise ValueError(msg)
        return v

    @model_validator(mode="after")
    def _default_registry_id(self) -> SourceConfig:
        if self.registry_id is None:
            self.registry_id = self.name
        return self


@functools.lru_cache(maxsize=1)
def load_source_configs() -> dict[str, SourceConfig]:
    """Load every `sources/*.yaml` into a {name: SourceConfig} map (cached)."""
    configs: dict[str, SourceConfig] = {}
    for path in sorted(_CONFIG_DIR.glob("*.yaml")):
        raw: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        cfg = SourceConfig.model_validate(raw)
        if cfg.name in configs:
            msg = f"Duplicate source config '{cfg.name}' ({path.name})"
            raise ValueError(msg)
        configs[cfg.name] = cfg
    return configs


def get_source_config(name: str) -> SourceConfig:
    """Return one provider's config, raising KeyError if absent."""
    return load_source_configs()[name]
