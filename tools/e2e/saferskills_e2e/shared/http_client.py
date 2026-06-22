"""Async httpx client factory + transient-retry wrapper.

Single entry point so every command pays the same timeout + User-Agent
posture. Commands `async with make_client(config) as client:` to
guarantee the connection pool is closed.

`request_with_retries` absorbs TRANSIENT failures (a connect/read timeout, a
ConnectError, or a 502/503/504) so a momentary staging blip — e.g. the shared
Postgres saturating for a few seconds under ingestion load — doesn't red-gate a
prod deploy. It deliberately does NOT mask a sustained outage: a 4xx, any other
status, or a still-degraded API after the last attempt is returned/raised as-is,
so real breakage still fails the gate (the chosen contract).
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx

from saferskills_e2e.shared.config import Config

USER_AGENT = "saferskills-e2e/0.0"

# Statuses that mean "the API is up but momentarily degraded" — safe to retry.
# A 5xx that is NOT one of these (e.g. 500) is a real error and passes through.
_TRANSIENT_STATUS = frozenset({502, 503, 504})


def make_client(config: Config) -> httpx.AsyncClient:
    """Return an unauthenticated async HTTP client.

    The timeout is the config-derived per-request budget. The
    `User-Agent` makes E2E traffic trivially filterable in server logs.
    `follow_redirects=True` matches what a real browser would do for
    the marketing site (e.g. `/` -> `/index.html`).
    """
    return httpx.AsyncClient(
        timeout=config.request_timeout_seconds,
        headers={"User-Agent": USER_AGENT},
        follow_redirects=True,
    )


async def request_with_retries(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    *,
    retries: int = 3,
    backoff: float = 1.0,
    **kwargs: Any,
) -> httpx.Response:
    """Issue a request, retrying ONLY transient failures with exponential backoff.

    Transient = `httpx.ConnectError` / `httpx.TimeoutException`, or a 502/503/504
    response. Everything else (a 2xx, a 4xx, any other 5xx) is returned straight
    away — no retry. `retries` is the number of ATTEMPTS (3 → sleeps of `backoff`,
    `2*backoff` before the 2nd/3rd try). On the LAST attempt the result is returned
    (even a 503) or the exception re-raised, so a SUSTAINED degradation still
    surfaces to the caller and fails the command — only transient blips are masked.
    """
    retries = max(1, retries)
    for attempt in range(retries):
        try:
            resp = await client.request(method, url, **kwargs)
        except httpx.ConnectError, httpx.TimeoutException:
            if attempt == retries - 1:
                raise  # sustained — let the caller's error handling fail the command
        else:
            if resp.status_code not in _TRANSIENT_STATUS or attempt == retries - 1:
                return resp  # success, a non-transient status, OR the final attempt
        await asyncio.sleep(backoff * (2.0**attempt))
    # The loop always returns or raises on its final iteration (retries >= 1).
    raise RuntimeError("request_with_retries exhausted without returning")
