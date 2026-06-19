"""Per-source token-bucket rate limiter for scrape fetches (ToS-respect #5).

The HTTPX client's request hook (`http_client._rate_limit_hook`) gates the tier-0
feed/sitemap fetches that go through the shared HTTPX client. The tier-1 HTML
fetches go through curl_cffi (a separate client that bypasses the HTTPX request
hooks), so they need their own throttle: `acquire_scrape_slot(source, rate)`.

Keyed by source name and shared across cycles (module-level state), so a source's
rate ceiling holds across concurrent jobs + sequential cycles. `rate` is requests
per second (the YAML `rate_limit_per_second`, default 0.1 = 1 req / 10s).
"""

from __future__ import annotations

import asyncio
import time

# Per-source coordination (keyed by source name) — survives across cycles.
_LOCKS: dict[str, asyncio.Lock] = {}
_LAST_REQUEST_TS: dict[str, float] = {}


async def acquire_scrape_slot(source: str, rate: float) -> None:
    """Block until at least `1/rate` seconds have elapsed since this source's last
    scrape slot, then stamp the current time. A non-positive rate is treated as
    unthrottled (returns immediately)."""
    if rate <= 0:
        return
    min_interval = 1.0 / rate
    lock = _LOCKS.setdefault(source, asyncio.Lock())
    async with lock:
        now = time.monotonic()
        last = _LAST_REQUEST_TS.get(source, 0.0)
        wait = (last + min_interval) - now
        if wait > 0:
            await asyncio.sleep(wait)
        _LAST_REQUEST_TS[source] = time.monotonic()


def reset_scrape_slots() -> None:
    """Clear all per-source timing state (test helper)."""
    _LAST_REQUEST_TS.clear()
