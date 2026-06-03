"""enqueue_ingest_task — the webhook fan-out task (D-04-04).

Two-step (D-04-04): ingestion is decoupled from the auto-scan trigger. This task
applies a webhook payload to catalog_items + ingestion_events ONLY. The Phase C
popularity_recompute job decides which items get Lite/Deep scans. Adapters running
their own periodic cycle call MergeEngine.upsert directly (see RegistryAdapter);
this path is for the GitHub webhook handler in app/routers/webhooks.py.
"""

from __future__ import annotations

from typing import Any, cast

from procrastinate.retry import RetryStrategy

from app.ingestion import procrastinate_app
from app.ingestion.framework.base_adapter import NormalizedItem, RawItem
from app.ingestion.framework.retry import IngestionRetry
from app.ingestion.sources.github_skills_webhook import GithubSkillsWebhookAdapter


@procrastinate_app.task(
    queue="ingest_github",
    retry=cast(
        RetryStrategy, IngestionRetry()
    ),  # IngestionRetry is BaseRetryStrategy; RetryValue type is too narrow
)
async def enqueue_ingest_task(*, source: str, raw_payload: dict[str, Any]) -> dict[str, str]:
    """Apply one webhook payload through the merger + outbox, in one transaction."""
    from app.db.session import AsyncSessionLocal
    from app.ingestion.config.loader import get_source_config
    from app.ingestion.framework.content_hash import compute_artifact_hash
    from app.ingestion.framework.merger import MergeEngine
    from app.ingestion.framework.outbox import OutboxWriter

    adapter = GithubSkillsWebhookAdapter(get_source_config(source))
    async with AsyncSessionLocal() as session:
        raw_result: tuple[RawItem, NormalizedItem | None] = await adapter.handle_webhook(
            raw_payload, session
        )
        raw: RawItem = raw_result[0]
        normalized: NormalizedItem | None = raw_result[1]
        raw_hash = compute_artifact_hash(normalized.metadata_files) if normalized else "0" * 64
        outcome = "noop"
        if normalized is not None:
            outcome = await MergeEngine(session).upsert(
                normalized, raw_hash=raw_hash, source=source
            )
        await OutboxWriter(session, source=source).append(raw, normalized=normalized, applied=True)
        await session.commit()
    return {"outcome": outcome}
