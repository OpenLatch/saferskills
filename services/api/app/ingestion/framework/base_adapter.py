"""Base contract every ingestion adapter inherits — parameterised by SourceConfig.

Repo vs capability keys (migration 0007 — one catalog_item = one capability):
  - Adapters key the REPO-LEVEL FETCH on (github_org, github_repo) — the unit a
    registry/topic/webhook surfaces.
  - The scan engine fans a repo into N capabilities; the MergeEngine upsert/dedup
    target is the CAPABILITY slug `<org>--<repo>--<kind>-<name>[-<hash6>]`. Several
    capabilities legitimately share one github_url (UNIQUE(github_url) dropped in 0007).

Adapters declare nothing as ClassVars — every knob (hosts, cadence, rate limit,
kind, discovery params) comes from the YAML `SourceConfig`. Adapters implement
`list_items(client)` + `normalize(raw)`. Provider classes register themselves in
ADAPTER_REGISTRY via `@register_adapter`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from typing import Any, TypeVar, cast

from app.ingestion.config.loader import SourceConfig

_T = TypeVar("_T", bound="BaseAdapter")


@dataclass
class RawItem:
    """What the adapter observed before normalization (one per fetch)."""

    source_id: str
    raw_body_bytes: bytes
    raw_body_hash: str
    etag: str | None = None
    fetched_at: str = ""
    http_status: int = 200
    duration_ms: int = 0
    from_cache: bool = False
    fetch_tier: int = 1
    payload_hint: dict[str, Any] = field(default_factory=cast("type[dict[str, Any]]", dict))
    error_reason: str | None = None


@dataclass
class NormalizedItem:
    """The canonical shape an adapter produces for the merger."""

    github_org: str | None
    github_repo: str | None
    display_name: str
    description: str = ""  # ≤ 280 chars; never the raw aggregator body
    license_spdx: str | None = None
    github_url: str | None = None
    source_url: str | None = None
    kind: str | None = None  # adapter hint; classifier finalises when None
    component_path: str | None = None
    stars: int | None = None
    star_velocity_7d: float | None = None
    weekly_downloads: int | None = None
    pushed_at: str | None = None
    default_branch: str | None = None
    repo_archived: bool = False
    repo_yanked: bool = False
    metadata_files: dict[str, bytes] = field(default_factory=cast("type[dict[str, bytes]]", dict))
    aggregator_listings: list[str] = field(default_factory=cast("type[list[str]]", list))
    payload_hint: dict[str, Any] = field(
        default_factory=cast("type[dict[str, Any]]", dict)
    )  # commit_count, is_fork_only, …


class BaseAdapter(ABC):
    """Config-driven adapter base. Construct with the provider's SourceConfig."""

    def __init__(self, config: SourceConfig) -> None:
        self.config = config

    # Convenience accessors (read from the YAML-loaded config).
    @property
    def source_name(self) -> str:
        return self.config.name

    @property
    def source_hosts(self) -> set[str]:
        return set(self.config.hosts)

    @property
    def cadence_cron(self) -> str | None:
        return self.config.cadence_cron

    @property
    def rate_limit_per_second(self) -> float:
        return self.config.rate_limit_per_second

    @property
    def source_kind(self) -> str:
        return self.config.kind

    @abstractmethod
    def list_items(self, client: Any) -> AsyncIterator[RawItem]:
        """Yield every item the source currently lists. Resumable via crawler_cursors."""
        ...

    @abstractmethod
    def normalize(self, raw: RawItem) -> NormalizedItem | None:
        """Convert a source-specific payload to the canonical shape (None to skip)."""
        ...

    async def enrich(self, client: Any, normalized: NormalizedItem) -> None:
        """Optional follow-up fetch to populate `metadata_files` (manifests) for the
        classifier + content hash. Default no-op; adapters override where the listing
        response lacks manifest bytes (e.g. github_topics fetches raw.githubusercontent)."""
        return None


# Provider adapter registry — each source module registers its class here so
# tasks.py can build periodic tasks by looping the YAML configs (config-first).
ADAPTER_REGISTRY: dict[str, type[BaseAdapter]] = {}


def register_adapter(source_name: str) -> Callable[[type[_T]], type[_T]]:
    """Class decorator: register an adapter class under its source name.

    The generic TypeVar preserves the concrete subclass type so pyright
    resolves the decorated class as its own type, not the base type.
    """

    def _wrap(cls: type[_T]) -> type[_T]:
        ADAPTER_REGISTRY[source_name] = cls
        return cls

    return _wrap


def build_adapter(source_name: str) -> BaseAdapter:
    """Instantiate the registered adapter for a source with its YAML config."""
    from app.ingestion.config.loader import get_source_config

    cls = ADAPTER_REGISTRY[source_name]
    return cls(get_source_config(source_name))
