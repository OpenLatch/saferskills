"""WebhookAdapter — superclass for webhook-driven sources (github_skills).

Webhook adapters have no cadence (CADENCE_CRON is null in their YAML). They
translate an inbound webhook payload into a (RawItem, NormalizedItem) pair via
`handle_webhook`, which the enqueue task applies through the same MergeEngine +
OutboxWriter path as a registry cycle. `list_items`/`normalize` are unused (the
payload IS the listing), so they default to no-ops here.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.ingestion.framework.base_adapter import BaseAdapter, NormalizedItem, RawItem


class WebhookAdapter(BaseAdapter):
    async def list_items(self, client: Any) -> AsyncIterator[RawItem]:  # pragma: no cover
        return
        yield  # type: ignore[unreachable]

    def normalize(self, raw: RawItem) -> NormalizedItem | None:  # pragma: no cover
        return None

    async def handle_webhook(
        self, payload: dict[str, Any], session: AsyncSession
    ) -> tuple[RawItem, NormalizedItem | None]:
        """Translate an inbound webhook payload into (RawItem, NormalizedItem|None)."""
        raise NotImplementedError
