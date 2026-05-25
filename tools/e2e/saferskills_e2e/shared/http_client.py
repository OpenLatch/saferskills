"""Async httpx client factory.

Single entry point so every command pays the same timeout + User-Agent
posture. Commands `async with make_client(config) as client:` to
guarantee the connection pool is closed.
"""

from __future__ import annotations

import httpx

from saferskills_e2e.shared.config import Config

USER_AGENT = "saferskills-e2e/0.0"


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
