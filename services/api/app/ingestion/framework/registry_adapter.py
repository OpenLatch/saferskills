"""RegistryAdapter — superclass for API-first sources (github_topics, mcp_registry,
npm, pypi). Provides the run-one-cycle loop the Procrastinate task wraps with
retry + queueing-lock. Drives: list_items → normalize → enrich → content hash →
MergeEngine.upsert, writing one ingestion_events row per fetch in the same tx as
the catalog upsert.

Robustness overhaul (WS-5 + WS-6):
  - **Two-phase batching (WS-6).** Each batch is first PREPARED entirely outside any
    open transaction — `normalize()` + `enrich()` (the multi-fetch, 60s-timeout
    network step) hold NO pooled DB connection — then WRITTEN in one short
    transaction (upsert + outbox per item) and committed. Previously the loop held a
    pooled connection across every item's enrich I/O for a whole batch, starving the
    shared pool the public API serves from. Phase boundaries keep the per-item outbox
    invariant (catalog row + its ingestion_events row in one commit) per batch
    (D-04-08); batching never splits a pair across commits.
  - **Per-item isolation (WS-5).** One poisoned item in a 10k-item crawl (a
    `ValueError`/`KeyError`/`TypeError`/`AttributeError` from provider shape-drift in
    normalize/enrich/upsert) becomes ONE clean `ingestion.item_skipped` WARN + a
    skipped outbox row + `continue` — never a whole-cycle traceback + retry storm.
    A collect-phase skip is pre-DB (clean session); a write-phase skip rolls back
    just that item's SAVEPOINT so the rest of the batch survives.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.ingestion.framework.base_adapter import BaseAdapter, NormalizedItem, RawItem
from app.ingestion.framework.content_hash import compute_artifact_hash
from app.ingestion.framework.http_client import HttpClientFactory
from app.ingestion.framework.merger import MergeEngine
from app.ingestion.framework.outbox import OutboxWriter

logger = structlog.get_logger(__name__)

# Commit every N processed items rather than once at the end of the cycle. A
# full-feed source (mcp_registry ~10k items, each doing per-item enrich fetches)
# would otherwise hold one giant transaction for the whole crawl: nothing is
# durable or visible until it finishes, and any failure rolls back the entire
# batch. Batching bounds the transaction size and surfaces progress incrementally.
_COMMIT_BATCH = 25

# Provider shape-drift surfaces as these; per-item isolation skips the one item
# rather than letting it abort the cycle (WS-5). Deliberately NOT catching
# DBAPIError / httpx errors here — those are transient/infra and belong to the
# cycle-level handling in `tasks.run_source_cycle`.
_ITEM_SKIP_EXCEPTIONS = (ValueError, KeyError, TypeError, AttributeError)


@dataclass
class _PreparedItem:
    """One item after the network/transform phase, ready for the DB write phase."""

    raw: RawItem
    normalized: NormalizedItem | None  # None ⇒ 304 / normalize-skip / poisoned
    raw_hash: str | None = None
    poisoned: bool = False  # shape-drift in collect phase — record seen, no upsert


class RegistryAdapter(BaseAdapter):
    async def run_cycle(self, session: AsyncSession, settings: Any) -> dict[str, int]:
        counters = {
            "items_seen": 0,
            "items_added": 0,
            "items_updated": 0,
            "items_skipped": 0,
            "http_304_count": 0,
            "http_5xx_count": 0,
        }
        outbox = OutboxWriter(session, source=self.source_name)
        merger = MergeEngine(session)
        client = HttpClientFactory.build(self, settings)
        async with client:
            batch: list[_PreparedItem] = []
            async for raw in self.list_items(client):
                counters["items_seen"] += 1
                # PHASE 1 — prepare (network + transform), NO DB connection held.
                batch.append(await self._prepare_item(client, raw, counters))
                if len(batch) >= _COMMIT_BATCH:
                    # PHASE 2 — write the batch in one short transaction + commit.
                    await self._write_batch(session, merger, outbox, batch, counters)
                    batch = []
            if batch:
                await self._write_batch(session, merger, outbox, batch, counters)
        return counters

    async def _prepare_item(
        self, client: Any, raw: RawItem, counters: dict[str, int]
    ) -> _PreparedItem:
        """Network + transform for one item (no DB). Counts 304/5xx; normalizes +
        enriches + hashes. A shape-drift error here is isolated to this item: ONE
        clean WARN + a poisoned marker (recorded as a skipped outbox row in the
        write phase). The session is untouched, so the batch stays writable."""
        if raw.http_status == 304:
            counters["http_304_count"] += 1
            return _PreparedItem(raw=raw, normalized=None)
        if 500 <= raw.http_status < 600:
            counters["http_5xx_count"] += 1
        try:
            normalized = self.normalize(raw)
            if normalized is None:
                return _PreparedItem(raw=raw, normalized=None)
            await self.enrich(client, normalized)
            raw_hash = compute_artifact_hash(normalized.metadata_files)
            return _PreparedItem(raw=raw, normalized=normalized, raw_hash=raw_hash)
        except _ITEM_SKIP_EXCEPTIONS as exc:
            counters["items_skipped"] += 1
            logger.warning(
                "ingestion.item_skipped",
                source=self.source_name,
                phase="prepare",
                reason=type(exc).__name__,
                error=str(exc)[:200],
                source_id=raw.source_id,
            )
            return _PreparedItem(raw=raw, normalized=None, poisoned=True)

    async def _write_batch(
        self,
        session: AsyncSession,
        merger: MergeEngine,
        outbox: OutboxWriter,
        batch: list[_PreparedItem],
        counters: dict[str, int],
    ) -> None:
        """Write one prepared batch (upsert + outbox per item) then commit. Each item
        is written inside a SAVEPOINT so a write-phase shape-drift error rolls back
        just that item (keeping its catalog+outbox pair atomic) and the batch survives.
        """
        for item in batch:
            try:
                async with session.begin_nested():
                    await self._write_one(merger, outbox, item, counters)
            except _ITEM_SKIP_EXCEPTIONS as exc:
                counters["items_skipped"] += 1
                logger.warning(
                    "ingestion.item_skipped",
                    source=self.source_name,
                    phase="write",
                    reason=type(exc).__name__,
                    error=str(exc)[:200],
                    source_id=item.raw.source_id,
                )
        await session.commit()

    async def _write_one(
        self,
        merger: MergeEngine,
        outbox: OutboxWriter,
        item: _PreparedItem,
        counters: dict[str, int],
    ) -> None:
        """The DB writes for one prepared item (runs inside a per-item SAVEPOINT)."""
        if item.normalized is None or item.poisoned:
            # 304 / normalize-skip / poisoned — record the fetch in the outbox only
            # (the per-fetch outbox invariant: one event per observed item).
            await outbox.append(item.raw, normalized=None, applied=True)
            return
        assert item.raw_hash is not None
        outcome = await merger.upsert(
            item.normalized, raw_hash=item.raw_hash, source=self.source_name
        )
        if outcome in ("added", "added_with_merge_candidate"):
            counters["items_added"] += 1
        elif outcome == "updated":
            counters["items_updated"] += 1
        await outbox.append(item.raw, normalized=item.normalized, applied=True)
