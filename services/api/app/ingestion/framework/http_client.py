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
import ipaddress
import time
from typing import Any

import httpx
from hishel import AsyncSqliteStorage, CacheOptions, SpecificationPolicy
from hishel.httpx import AsyncCacheTransport

from app.core.config import Settings
from app.ingestion.framework.base_adapter import BaseAdapter
from app.ingestion.framework.exceptions import BodyTooLargeError, OutboundDenyError

_MAX_BODY_BYTES = 26_214_400  # 25 MiB
_PRIVATE_NETS = (
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("::1/128"),
)

# Per-source coordination (keyed by source name) — survives across cycles.
_SEMAPHORES: dict[str, asyncio.Semaphore] = {}
_LAST_REQUEST_TS: dict[str, float] = {}
# In-process GitHub App installation-token cache (token, monotonic-expiry).
_GITHUB_APP_TOKEN: dict[str, tuple[str, float]] = {}


class _SSRFTransport(httpx.AsyncHTTPTransport):
    """Enforce the per-adapter host allowlist + a private-IP denylist before each request."""

    def __init__(self, allowlist: set[str]) -> None:
        super().__init__()
        self._allowlist = {h.lower() for h in allowlist}

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        host = (request.url.host or "").lower()
        if host not in self._allowlist:
            raise OutboundDenyError(
                f"OUTBOUND DENY: {host} not in allowlist {sorted(self._allowlist)}"
            )
        try:
            ip = ipaddress.ip_address(host)
            if any(ip in net for net in _PRIVATE_NETS):
                raise OutboundDenyError(f"SSRF DENY: private IP {host}")
        except ValueError:
            pass  # hostname (not a literal IP) — allowlist already gated it
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
    if cl is not None and int(cl) > _MAX_BODY_BYTES:
        raise BodyTooLargeError(f"BODY TOO LARGE: {cl} bytes from {response.url}")


def _github_app_token_hook(settings: Settings) -> Any:
    async def hook(request: httpx.Request) -> None:
        token = await _get_github_app_installation_token(settings)
        if token:
            request.headers["Authorization"] = f"Bearer {token}"
            request.headers["Accept"] = "application/vnd.github+json"
            request.headers["X-GitHub-Api-Version"] = "2022-11-28"

    return hook


async def _get_github_app_installation_token(settings: Settings) -> str | None:
    """Mint (and cache 50 min) a GitHub App installation token. None if creds absent."""
    app_id: str | None = getattr(settings, "github_app_id", None)
    private_key: str | None = getattr(settings, "github_app_private_key", None)
    installation_id: str | None = getattr(settings, "github_app_installation_id", None)
    if not (app_id and private_key and installation_id):
        return None
    cached = _GITHUB_APP_TOKEN.get("token")
    if cached is not None and cached[1] > time.monotonic() + 60.0:
        return cached[0]

    import jwt

    now = int(time.time())
    payload: dict[str, int | str] = {"iat": now - 30, "exp": now + 60 * 9, "iss": app_id}
    jwt_token: str = jwt.encode(payload, private_key, algorithm="RS256")
    async with httpx.AsyncClient(timeout=20.0) as raw:
        r = await raw.post(
            f"https://api.github.com/app/installations/{installation_id}/access_tokens",
            headers={
                "Authorization": f"Bearer {jwt_token}",
                "Accept": "application/vnd.github+json",
            },
        )
        r.raise_for_status()
        data: dict[str, Any] = r.json()
        token: str = data["token"]
    _GITHUB_APP_TOKEN["token"] = (token, time.monotonic() + 60 * 50)
    return token
