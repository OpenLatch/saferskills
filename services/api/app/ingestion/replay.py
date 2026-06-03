"""Outbox replay — re-derive the catalog from ingestion_events (D-04-08).

`python -m app.ingestion.replay --since <iso> [--apply | --dry-run]`

Reads ingestion_events ordered by fetched_at and re-applies each event's
normalized payload through the MergeEngine. `--dry-run` (default) reports what
would change without writing; `--apply` commits. Recovery tool after a merger bug.

Note: payloads store metadata-file *hashes*, not bytes (no-raw-payload invariant),
so the content hash is reconstructed from those hashes; kind/quality re-classify
from the available signals. Catalog rows + attributions are rebuilt; byte-level
manifest re-derivation needs a source re-fetch.
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import hashlib
from typing import Any

import rfc8785
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import AsyncSessionLocal
from app.ingestion.framework.base_adapter import NormalizedItem
from app.ingestion.framework.merger import MergeEngine
from app.models import IngestionEvent

logger = structlog.get_logger(__name__)


def _hash_from_payload(payload: dict[str, Any]) -> str:
    raw_hashes: Any = payload.get("metadata_file_hashes") or {}
    file_hashes: dict[str, Any] = {k: v for k, v in raw_hashes.items() if k != "_omitted"}
    if not file_hashes:
        return hashlib.sha256(b"").hexdigest()
    return hashlib.sha256(rfc8785.dumps(dict(sorted(file_hashes.items())))).hexdigest()


def _normalized_from_payload(payload: dict[str, Any]) -> NormalizedItem:
    return NormalizedItem(
        github_org=payload.get("github_org"),
        github_repo=payload.get("github_repo"),
        display_name=payload.get("display_name") or "",
        description=payload.get("description") or "",
        license_spdx=payload.get("license_spdx"),
        github_url=payload.get("github_url"),
        source_url=payload.get("source_url"),
        stars=payload.get("stars"),
        weekly_downloads=payload.get("weekly_downloads"),
        pushed_at=payload.get("pushed_at"),
        repo_archived=bool(payload.get("repo_archived")),
        repo_yanked=bool(payload.get("repo_yanked")),
        aggregator_listings=payload.get("aggregator_listings") or [],
    )


async def replay(
    since: dt.datetime, *, apply: bool, session: AsyncSession | None = None
) -> dict[str, int]:
    """Re-apply ingestion_events into the catalog.

    When `session` is provided (tests), replay runs inside the caller's transaction
    and never commits/rolls back — the caller owns the tx (a flush makes upserts
    visible when apply=True). When `session` is None (CLI), replay opens its own
    AsyncSessionLocal and commits (apply) or rolls back (dry-run).
    """
    if session is not None:
        return await _replay_core(session, since, apply=apply, owns_tx=False)
    async with AsyncSessionLocal() as own_session:
        return await _replay_core(own_session, since, apply=apply, owns_tx=True)


async def _replay_core(
    session: AsyncSession, since: dt.datetime, *, apply: bool, owns_tx: bool
) -> dict[str, int]:
    counts = {"events": 0, "added": 0, "updated": 0, "skipped": 0}
    merger = MergeEngine(session)
    rows = (
        await session.execute(
            select(IngestionEvent)
            .where(IngestionEvent.fetched_at >= since, IngestionEvent.payload.isnot(None))
            .order_by(IngestionEvent.fetched_at.asc())
        )
    ).scalars()
    for event in rows:
        counts["events"] += 1
        payload = event.payload or {}
        if not payload.get("github_org"):
            counts["skipped"] += 1
            continue
        n = _normalized_from_payload(payload)
        outcome = await merger.upsert(n, raw_hash=_hash_from_payload(payload), source=event.source)
        if outcome.startswith("added"):
            counts["added"] += 1
        elif outcome == "updated":
            counts["updated"] += 1
    if owns_tx:
        if apply:
            await session.commit()
        else:
            await session.rollback()
    elif apply:
        await session.flush()
    return counts


def main() -> int:
    parser = argparse.ArgumentParser(description="Replay ingestion_events into the catalog.")
    parser.add_argument("--since", required=True, help="ISO 8601 cutoff (inclusive).")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--apply", action="store_true", help="Commit the re-applied state.")
    group.add_argument("--dry-run", action="store_true", help="Report only (default).")
    args = parser.parse_args()
    since = dt.datetime.fromisoformat(args.since.replace("Z", "+00:00"))
    if since.tzinfo is None:
        since = since.replace(tzinfo=dt.UTC)
    counts = asyncio.run(replay(since, apply=args.apply))
    logger.info("ingestion.replay_done", apply=args.apply, **counts)
    print(counts)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
