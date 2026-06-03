"""OutboxWriter — writes one ingestion_events row per fetch (D-04-08).

The row is written in the SAME transaction as any catalog_items upsert the fetch
produced; the caller (RegistryAdapter.run_cycle) commits once at the end. Payload
is bounded to ~64 KiB and NEVER contains raw metadata-file bytes — only their
per-file hashes (security.md § Scan-trace transparency stays no-raw-payload).
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from typing import Any

from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.ingestion.framework.base_adapter import NormalizedItem, RawItem
from app.models import IngestionEvent

_PAYLOAD_CAP = 65_536


def _sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


class OutboxWriter:
    def __init__(self, session: AsyncSession, source: str) -> None:
        self.session = session
        self.source = source

    async def append(self, raw: RawItem, normalized: NormalizedItem | None, applied: bool) -> None:
        payload: dict[str, Any] | None
        if normalized is None:
            payload = None
        else:
            payload = {
                "github_org": normalized.github_org,
                "github_repo": normalized.github_repo,
                "display_name": normalized.display_name,
                "description": normalized.description,
                "license_spdx": normalized.license_spdx,
                "github_url": normalized.github_url,
                "source_url": normalized.source_url,
                "stars": normalized.stars,
                "weekly_downloads": normalized.weekly_downloads,
                "pushed_at": normalized.pushed_at,
                "repo_archived": normalized.repo_archived,
                "repo_yanked": normalized.repo_yanked,
                "aggregator_listings": normalized.aggregator_listings,
                "fetch_tier": raw.fetch_tier,
                "duration_ms": raw.duration_ms,
                "from_cache": raw.from_cache,
                # NEVER persist metadata-file bytes — only their hashes.
                "metadata_file_hashes": {
                    fn: _sha256(b) for fn, b in (normalized.metadata_files or {}).items()
                },
            }
            if len(json.dumps(payload, separators=(",", ":"))) > _PAYLOAD_CAP:
                payload["metadata_file_hashes"] = {"_omitted": "payload-too-large"}

        now = dt.datetime.now(tz=dt.UTC)
        await self.session.execute(
            insert(IngestionEvent).values(
                source=self.source,
                source_id=raw.source_id[:500],
                http_status=raw.http_status,
                body_sha256=raw.raw_body_hash,
                etag=raw.etag,
                fetched_at=now,
                duration_ms=raw.duration_ms,
                from_cache=raw.from_cache,
                fetch_tier=raw.fetch_tier,
                payload=payload,
                applied_at=now if applied else None,
                error_reason=raw.error_reason,
            )
        )
