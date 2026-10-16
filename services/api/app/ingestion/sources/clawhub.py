"""Bounded public ClawHub catalog polling; no HTML scraping or skill downloads.

Contract: https://docs.openclaw.ai/clawhub/http-api#get-apiv1skills
The owner-qualified identity matters: different publishers can share a slug.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import AsyncIterator
from typing import Any, cast

from sqlalchemy.ext.asyncio import AsyncSession

from app.ingestion.config.loader import SourceConfig
from app.ingestion.framework.base_adapter import NormalizedItem, RawItem, register_adapter
from app.ingestion.framework.cursor import read_cursor, write_cursor
from app.ingestion.framework.registry_adapter import RegistryAdapter

_SEGMENT = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,199}\Z")


def _identity(record: dict[str, Any]) -> str | None:
    owner, slug = record.get("ownerHandle"), record.get("slug")
    if not isinstance(owner, str) or not isinstance(slug, str):
        return None
    if not _SEGMENT.fullmatch(owner) or not _SEGMENT.fullmatch(slug):
        return None
    return f"{owner}/{slug}"


def _listing_url(identity: str) -> str:
    owner, slug = identity.split("/", 1)
    return f"https://clawhub.ai/{owner}/skills/{slug}"


@register_adapter("clawhub")
class ClawhubAdapter(RegistryAdapter):
    """Traverse public skills in bounded, durably resumable cycles."""

    def __init__(self, config: SourceConfig) -> None:
        super().__init__(config)
        self.next_cursor: str | None = None
        self.completed = False

    async def run_cycle(self, session: AsyncSession, settings: Any) -> dict[str, int]:
        cursor = await read_cursor(session, self.source_name)
        self.next_cursor = cursor.get("next_cursor")
        self.completed = False
        # Release the read transaction before any remote I/O.
        await session.commit()
        counters = await super().run_cycle(session, settings)
        # All catalog/outbox batches are durable now. A failed chunk replays at
        # most max_items records; never checkpoint beyond an uncommitted tail.
        progress = {"next_cursor": self.next_cursor, "completed": self.completed}
        # Cycle health is independent of full-catalog exhaustion: a committed
        # bounded chunk is healthy even while completed remains false.
        await write_cursor(session, self.source_name, progress)
        await session.commit()
        return counters

    async def list_items(self, client: Any) -> AsyncIterator[RawItem]:
        discovery = self.config.discovery
        url = str(discovery["api_base"]).rstrip("/") + "/api/v1/skills"
        page_limit = max(1, min(int(discovery.get("page_limit", 50)), 200))
        max_items = max(1, min(int(discovery.get("max_items", 150)), 150))
        max_pages = max(1, min(int(discovery.get("max_pages", 10)), 10))
        cursor = self.next_cursor
        cursors: set[str] = {cursor} if cursor else set()
        identities: set[str] = set()
        for _ in range(max_pages):
            params = {
                "limit": str(min(page_limit, max_items - len(identities))),
                "sort": "createdAt",
            }
            if cursor:
                params["cursor"] = cursor
            response = await client.get(url, params=params)
            # HTTP failures must fail the cycle, not masquerade as an empty catalog.
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                raise ValueError("Invalid ClawHub catalog response")
            data = cast(dict[str, Any], payload)
            records = data.get("items")
            if not isinstance(records, list):
                raise ValueError("Invalid ClawHub catalog response")
            # The API must honor limit; failing closed avoids skipping any
            # excess records when persisting the page's continuation cursor.
            page_records = cast(list[Any], records)
            if len(page_records) > int(params["limit"]):
                raise ValueError("ClawHub response exceeded requested page limit")
            for value in page_records:
                if not isinstance(value, dict):
                    continue
                record = cast(dict[str, Any], value)
                identity = _identity(record)
                if identity is None or identity in identities:
                    continue
                identities.add(identity)
                body = json.dumps(record, sort_keys=True, separators=(",", ":")).encode()
                yield RawItem(
                    source_id=f"{self.source_name}/{_listing_url(identity)}",
                    raw_body_bytes=body,
                    raw_body_hash=hashlib.sha256(body).hexdigest(),
                    payload_hint=record,
                )
            next_cursor = data.get("nextCursor")
            if next_cursor is None:
                self.next_cursor = None
                self.completed = True
                return
            if not isinstance(next_cursor, str) or not next_cursor or len(next_cursor) > 8192:
                raise ValueError("Invalid ClawHub pagination cursor")
            if next_cursor in cursors:
                raise ValueError("Repeated ClawHub pagination cursor")
            cursors.add(next_cursor)
            cursor = next_cursor
            self.next_cursor = cursor
            if len(identities) >= max_items:
                return
            # Empty/short pages still have a continuation cursor (public filtering).

    def normalize(self, raw: RawItem) -> NormalizedItem | None:
        if raw.http_status != 200:
            return None
        record = raw.payload_hint
        identity = _identity(record)
        if identity is None or not isinstance(record.get("latestVersion"), dict):
            return None
        name = record.get("displayName")
        if not isinstance(name, str) or not name.strip():
            name = str(record["slug"])
        summary = record.get("summary")
        return NormalizedItem(
            github_org=None,
            github_repo=None,
            display_name=name.strip()[:200],
            description=summary[:280] if isinstance(summary, str) else "",
            source_url=_listing_url(identity),
            kind="skill",
            aggregator_listings=[self.source_name],
            registry_item_id=identity,
        )
