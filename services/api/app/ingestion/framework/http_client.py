"""HTTPX + Hishel (RFC-9111) + per-source rate-limit + SSRF-allowlist client factory.

Every adapter calls `HttpClientFactory.build(adapter, settings)` to get a client that:
  - caches per RFC 9111 (Hishel 1.x AsyncCacheTransport → AsyncSqliteStorage at
    settings.hishel_db_path); 304 revalidations cost 0 wire bytes vs the GitHub limit
  - enforces the per-adapter outbound allowlist (adapter.source_hosts) + a private-IP
    denylist at the transport layer (SSRF guard, security.md #2)
  - honours the per-source rate limit (asyncio.Semaphore + min-interval token bucket)
  - sends the declared User-Agent + From headers
  - rejects response bodies > 25 MiB (security.md #3)
  - injects a GitHub App installation token when the adapter fetches api.github.com
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

import httpx
from hishel import AsyncSqliteStorage, CacheOptions, SpecificationPolicy
from hishel.httpx import AsyncCacheTransport

from app.core.config import Settings
from app.core.github_app_token import get_github_app_installation_token
from app.ingestion.framework.allowlist import assert_host_allowed
from app.ingestion.framework.base_adapter import BaseAdapter
from app.ingestion.framework.exceptions import BodyTooLargeError

_MAX_BODY_BYTES = 26_214_400  # 25 MiB

# Per-source coordination (keyed by source name) — survives across cycles.
_SEMAPHORES: dict[str, asyncio.Semaphore] = {}
_LAST_REQUEST_TS: dict[str, float] = {}


class _SSRFTransport(httpx.AsyncHTTPTransport):
    """Enforce the per-adapter host allowlist + a private-IP denylist before each request.

    Delegates to the shared `allowlist.assert_host_allowed` (single source of truth,
    also called directly by the curl_cffi scrape fetches that bypass this transport)."""

    def __init__(self, allowlist: set[str]) -> None:
        super().__init__()
        self._allowlist = {h.lower() for h in allowlist}

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        assert_host_allowed(str(request.url), self._allowlist)
        return await super().handle_async_request(request)


def _ttl_for(adapter: BaseAdapter, settings: Settings) -> float:
    return float(
        settings.hishel_aggregator_ttl_seconds
        if adapter.source_kind == "scrape"
        else settings.hishel_github_ttl_seconds
    )


class HttpClientFactory:
    @classmethod
    def build(cls, adapter: BaseAdapter, settings: Settings) -> httpx.AsyncClient:
        storage = AsyncSqliteStorage(
            database_path=settings.hishel_db_path, default_ttl=_ttl_for(adapter, settings)
        )
        policy = SpecificationPolicy(cache_options=CacheOptions(shared=True, allow_stale=True))
        transport = AsyncCacheTransport(
            next_transport=_SSRFTransport(adapter.source_hosts),
            storage=storage,
            policy=policy,
        )
        request_hooks: list[Any] = [_rate_limit_hook(adapter)]
        # Exact host match over the allowlist set (NOT a substring/`in` URL check —
        # CodeQL py/incomplete-url-substring-sanitization). source_hosts is a set of
        # bare hostnames, so this is exact membership; `any(==)` makes that unambiguous.
        if any(host == "api.github.com" for host in adapter.source_hosts):
            request_hooks.append(_github_app_token_hook(settings))
        return httpx.AsyncClient(
            transport=transport,
            headers={
                "User-Agent": "SaferSkillsBot/1.0 (+https://saferskills.ai/bot)",
                "From": "bot@saferskills.ai",
                "Accept": "application/json, text/html",
            },
            timeout=httpx.Timeout(connect=30.0, read=60.0, write=30.0, pool=30.0),
            limits=httpx.Limits(max_keepalive_connections=10, max_connections=20),
            event_hooks={"request": request_hooks, "response": [_body_size_cap_hook]},
        )


def _rate_limit_hook(adapter: BaseAdapter) -> Any:
    name: str = adapter.source_name
    rate: float = adapter.rate_limit_per_second
    sem: asyncio.Semaphore = _SEMAPHORES.setdefault(name, asyncio.Semaphore(4))
    min_interval: float = 1.0 / rate if rate > 0 else 0.0

    async def hook(request: httpx.Request) -> None:
        async with sem:
            now = time.monotonic()
            last: float = _LAST_REQUEST_TS.get(name, 0.0)
            wait: float = (last + min_interval) - now
            if wait > 0:
                await asyncio.sleep(wait)
            _LAST_REQUEST_TS[name] = time.monotonic()

    return hook


async def _body_size_cap_hook(response: httpx.Response) -> None:
    cl = response.headers.get("content-length")
    if cl is None:
        return
    # A malformed Content-Length (non-numeric) must not raise inside the response
    # hook (WS-8a) — treat it as unknown size and let the stream/read path handle it.
    try:
        size = int(cl.strip())
    except ValueError:
        return
    if size > _MAX_BODY_BYTES:
        raise BodyTooLargeError(f"BODY TOO LARGE: {cl} bytes from {response.url}")


def _github_app_token_hook(settings: Settings) -> Any:
    async def hook(request: httpx.Request) -> None:
        token = await get_github_app_installation_token(settings)
        if token:
            request.headers["Authorization"] = f"Bearer {token}"
            request.headers["Accept"] = "application/vnd.github+json"
            request.headers["X-GitHub-Api-Version"] = "2022-11-28"

    return hook
