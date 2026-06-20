"""IndexNow Procrastinate task — fire-and-forget search-engine ping.

A new public, real-data page (a completed user/drift/appeal scan + its items) is
worth telling Bing/Yandex/etc. about so the Bing→ChatGPT surface picks it up
quickly. The actual HTTP POST runs in a durable Procrastinate job so a slow /
failing IndexNow endpoint never blocks the scan-completion path.

Registration (both in `app/ingestion/__init__.py`):
  - `"app.ingestion.tasks_indexnow"` in `import_paths` (so the worker knows the task)
  - `"indexnow"` in `ALL_QUEUES` (so `worker_main` drains the queue)
"""

from __future__ import annotations

from typing import Any, cast

import structlog

from app.ingestion import procrastinate_app

logger = structlog.get_logger(__name__)


@procrastinate_app.task(name="ping_indexnow", queue="indexnow", retry=3)
async def ping_indexnow(urls: list[str]) -> None:
    """Submit a URL set to IndexNow (no-op without a configured key)."""
    from app.seo.indexnow import submit_urls

    await submit_urls(urls)


async def defer_indexnow_ping(urls: list[str]) -> None:
    """Best-effort defer of a `ping_indexnow` job, deduped per first URL.

    Mirrors `defer_scan_job`: a `queueing_lock` keyed on the first URL makes a
    second enqueue for the same page a no-op while one is still queued. Never
    raises — a defer failure must not break the scan-completion caller.
    """
    if not urls:
        return
    lock = f"indexnow:{urls[0]}"
    try:
        # `urls` is a list[str]; defer_async types the kwarg as the broader
        # JSONValue (invariant list), so cast the JSON-serializable list.
        await ping_indexnow.configure(queueing_lock=lock).defer_async(urls=cast(Any, urls))
    except Exception:
        logger.debug("defer_indexnow_ping.skipped", count=len(urls))
