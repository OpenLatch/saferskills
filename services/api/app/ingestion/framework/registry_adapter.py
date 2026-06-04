"""RegistryAdapter — superclass for API-first sources (github_topics, mcp_registry,
npm, pypi). Provides the run-one-cycle loop the Procrastinate task wraps with
retry + queueing-lock. Drives: list_items → normalize → enrich → content hash →
MergeEngine.upsert, writing one ingestion_events row per fetch in the same tx as
the catalog upsert. Commits in batches of `_COMMIT_BATCH` items (not once at the
very end) so a long full-feed crawl is durable + visible incrementally and a
mid-crawl failure keeps the committed prefix — the per-item outbox invariant
(catalog row + its ingestion_events row in one commit) holds within each batch
(D-04-08).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.ingestion.framework.base_adapter import BaseAdapter
from app.ingestion.framework.content_hash import compute_artifact_hash
from app.ingestion.framework.http_client import HttpClientFactory
from app.ingestion.framework.merger import MergeEngine
from app.ingestion.framework.outbox import OutboxWriter

# Commit every N processed items rather than once at the end of the cycle. A
# full-feed source (mcp_registry ~10k items, each doing per-item enrich fetches)
# would otherwise hold one giant transaction for the whole crawl: nothing is
# durable or visible until it finishes, and any failure rolls back the entire
# batch. Batching keeps each item's catalog upsert + its ingestion_events row in
# the same commit (the D-04-08 outbox invariant holds per item), bounds the
# transaction size, and surfaces progress incrementally.
_COMMIT_BATCH = 25


class RegistryAdapter(BaseAdapter):
    async def run_cycle(self, session: AsyncSession, settings: Any) -> dict[str, int]:
        counters = {
            "items_seen": 0,
            "items_added": 0,
            "items_updated": 0,
            "http_304_count": 0,
            "http_5xx_count": 0,
        }
        outbox = OutboxWriter(session, source=self.source_name)
        merger = MergeEngine(session)
        client = HttpClientFactory.build(self, settings)
        async with client:
            async for raw in self.list_items(client):
                # Flush the prior batch before processing the next item, so a
                # crash mid-crawl keeps everything already committed (checked
                # here rather than at loop-end so the `continue` paths below
                # still count toward a batch boundary).
                if counters["items_seen"] > 0 and counters["items_seen"] % _COMMIT_BATCH == 0:
                    await session.commit()
                counters["items_seen"] += 1
                if raw.http_status == 304:
                    counters["http_304_count"] += 1
                    await outbox.append(raw, normalized=None, applied=True)
                    continue
                if 500 <= raw.http_status < 600:
                    counters["http_5xx_count"] += 1
                normalized = self.normalize(raw)
                if normalized is None:
                    await outbox.append(raw, normalized=None, applied=True)
                    continue
                await self.enrich(client, normalized)
                raw_hash = compute_artifact_hash(normalized.metadata_files)
                outcome = await merger.upsert(
                    normalized, raw_hash=raw_hash, source=self.source_name
                )
                if outcome == "added" or outcome == "added_with_merge_candidate":
                    counters["items_added"] += 1
                elif outcome == "updated":
                    counters["items_updated"] += 1
                await outbox.append(raw, normalized=normalized, applied=True)
            await session.commit()
        return counters
