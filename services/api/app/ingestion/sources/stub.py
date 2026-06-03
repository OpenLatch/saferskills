"""StubAdapter — offline cycle testing helper.

Not registered in ADAPTER_REGISTRY (no @register_adapter decoration). Used by
tests and the `catalog ingest-stub` CLI subcommand (Phase A). Instantiate
directly with a SourceConfig whose `discovery.items` is a list of repo-JSON-
shaped dicts; yields nothing when the list is absent.

The normalize() method reuses the github_topics shape so the same test
assertions apply to both.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import AsyncIterator
from typing import Any, cast

import structlog

from app.ingestion.config.loader import SourceConfig
from app.ingestion.framework.base_adapter import NormalizedItem, RawItem
from app.ingestion.framework.registry_adapter import RegistryAdapter

logger = structlog.get_logger(__name__)


class StubAdapter(RegistryAdapter):
    """Replay canned repo-JSON items from `config.discovery['items']`."""

    def __init__(self, config: SourceConfig) -> None:
        super().__init__(config)

    async def list_items(self, client: Any) -> AsyncIterator[RawItem]:
        """Yield one RawItem per entry in `discovery.items` (or nothing if absent)."""
        items: list[dict[str, Any]] = self.config.discovery.get("items") or []
        for item in items:
            body = json.dumps(item, separators=(",", ":"), sort_keys=True).encode()
            full_name: str = item.get("full_name") or item.get("name") or "stub/unknown"
            yield RawItem(
                source_id=full_name,
                raw_body_bytes=body,
                raw_body_hash=hashlib.sha256(body).hexdigest(),
                http_status=200,
                fetch_tier=1,
                payload_hint=item,
            )

    def normalize(self, raw: RawItem) -> NormalizedItem | None:
        """Map a canned repo-JSON item to a NormalizedItem (github_topics shape)."""
        if raw.http_status != 200:
            return None
        item: dict[str, Any] = raw.payload_hint
        owner_raw: Any = item.get("owner")
        owner_obj: dict[str, Any] = (
            cast("dict[str, Any]", owner_raw) if isinstance(owner_raw, dict) else {}
        )
        org: str = str(owner_obj.get("login") or item.get("owner") or "")
        repo: str = str(item.get("name") or "")
        if not org or not repo:
            return None
        license_raw: Any = item.get("license")
        license_obj: dict[str, Any] = (
            cast("dict[str, Any]", license_raw) if isinstance(license_raw, dict) else {}
        )
        license_spdx: str | None = (
            str(license_obj.get("spdx_id")) if license_obj.get("spdx_id") else None
        )
        return NormalizedItem(
            github_org=org,
            github_repo=repo,
            display_name=repo,
            description=str(item.get("description") or "")[:280],
            license_spdx=license_spdx,
            github_url=str(item.get("html_url") or "") or None,
            source_url=str(item.get("html_url") or "") or None,
            stars=int(item["stargazers_count"])
            if "stargazers_count" in item and item["stargazers_count"] is not None
            else None,
            pushed_at=str(item.get("pushed_at") or "") or None,
            default_branch=str(item.get("default_branch") or "") or None,
            repo_archived=bool(item.get("archived", False)),
            metadata_files={},
            aggregator_listings=[self.config.name],
        )
