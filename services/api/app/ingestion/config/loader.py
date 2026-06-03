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
from pydantic import BaseModel, Field, field_validator

# The 14 crawled adapter sources (matches ingestion_events.source CHECK +
# crawler_cursors.source CHECK in migration 0011). user_submission/upload/
# vendor_verified are NOT crawled adapters (they are endpoints / attributions).
SOURCE_NAMES: frozenset[str] = frozenset(
    {
        "github_skills",
        "github_topics",
        "mcp_registry",
        "npm",
        "pypi",
        "mcp_so",
        "smithery",
        "glama",
        "pulsemcp",
        "clawhub",
        "skillsmp",
        "skills_sh",
        "claudeskills_info",
        "skillhub_club",
    }
)

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
