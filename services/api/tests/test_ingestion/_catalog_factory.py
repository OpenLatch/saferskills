"""Shared CatalogItem factory for ingestion tests."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from app.models.catalog_item import CatalogItem


def make_item(**over: Any) -> CatalogItem:
    """Build a fully-populated public-github CatalogItem; override any field."""
    now = dt.datetime.now(tz=dt.UTC)
    suffix = uuid.uuid4().hex[:8]
    fields: dict[str, Any] = {
        "kind": "mcp_server",
        "slug": f"acme--repo-{suffix}",
        "display_name": f"repo-{suffix}",
        "github_url": f"https://github.com/acme/repo-{suffix}",
        "github_org": "acme",
        "github_repo": f"repo-{suffix}",
        "default_branch": "main",
        "popularity_tier": "indexed",
        "popularity_score": 0,
        "popularity_rank_tier": "long_tail",
        "agent_compatibility": ["claude-code"],
        "quality_tier": "high",
        "quality_signals": {},
        "kind_signals": {},
        "availability": "available",
        "archived": False,
        "source_kind": "github",
        "visibility": "public",
        "content_hash_sha256": None,
        "consecutive404_count": 0,
        "last_seen200_at": now,
        "pushed_at": now,
        "github_stars": 0,
        "license_spdx": None,
        "popularity_breakdown": {},
        "sources": [
            {
                "registryId": "github_topics",
                "registryUrl": "",
                "firstIndexedAt": now.isoformat(),
                "lastSeenAt": now.isoformat(),
            }
        ],
        "item_metadata": {},
        "created_at": now - dt.timedelta(days=2),  # past the 1h lite-debounce window
        "updated_at": now,
    }
    fields.update(over)
    return CatalogItem(**fields)
