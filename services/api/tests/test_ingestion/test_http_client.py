"""Tests for app.ingestion.framework.http_client._SSRFTransport + shared cache storage."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from hishel import AsyncSqliteStorage, CacheOptions

from app.ingestion.framework.exceptions import OutboundDenyError
from app.ingestion.framework.http_client import (
    _SHARED_STORAGE,  # pyright: ignore[reportPrivateUsage]
    HttpClientFactory,
    _hishel_ttl_hook,  # pyright: ignore[reportPrivateUsage]
    _shared_storage,  # pyright: ignore[reportPrivateUsage]
    _SharedStorageCacheTransport,  # pyright: ignore[reportPrivateUsage]
    _SSRFTransport,  # pyright: ignore[reportPrivateUsage]
)


class TestSSRFTransport:
    @pytest.mark.asyncio
    async def test_deny_unknown_host_raises_outbound_deny_error(self) -> None:
        transport = _SSRFTransport({"api.github.com"})
        request = httpx.Request("GET", "https://evil.example.com/steal")
        with pytest.raises(OutboundDenyError, match=r"evil\.example\.com"):
            await transport.handle_async_request(request)

    @pytest.mark.asyncio
    async def test_deny_subdomain_not_in_allowlist(self) -> None:
        transport = _SSRFTransport({"api.github.com"})
        request = httpx.Request("GET", "https://sub.api.github.com/data")
        with pytest.raises(OutboundDenyError):
            await transport.handle_async_request(request)

    @pytest.mark.asyncio
    async def test_deny_empty_allowlist(self) -> None:
        transport = _SSRFTransport(set())
        request = httpx.Request("GET", "https://api.github.com/")
        with pytest.raises(OutboundDenyError):
            await transport.handle_async_request(request)

    @pytest.mark.asyncio
    async def test_allowlist_is_case_insensitive(self) -> None:
        """Allowlist should normalise to lowercase so UPPER-CASE hosts still deny."""
        transport = _SSRFTransport({"API.GITHUB.COM"})
        # api.github.com would be in the normalised set — passes allowlist check.
        # We just verify no OutboundDenyError for the allowed host.
        # (The real TCP call will fail — we only care that it doesn't raise ODE)
        request = httpx.Request("GET", "https://api.github.com/")
        try:
            await transport.handle_async_request(request)
        except OutboundDenyError:
            pytest.fail("OutboundDenyError raised for an allowlisted host")
        except Exception:
            pass  # Network error expected in unit tests — that's fine

    @pytest.mark.asyncio
    async def test_deny_http_internal_ip_as_host(self) -> None:
        """Even if a literal private IP somehow got through, it should be denied by the denylist."""
        transport = _SSRFTransport({"127.0.0.1"})
        request = httpx.Request("GET", "http://127.0.0.1/internal")
        # 127.0.0.1 is in the allowlist but also in PRIVATE_NETS → should raise SSRF DENY
        with pytest.raises(OutboundDenyError, match="SSRF DENY"):
            await transport.handle_async_request(request)


def _settings(db_path: str = "/tmp/test-hishel.db") -> MagicMock:
    s = MagicMock()
    s.hishel_db_path = db_path
    s.hishel_github_ttl_seconds = 86400
    s.hishel_aggregator_ttl_seconds = 3600
    return s


def _adapter(*, kind: str = "scrape", hosts: set[str] | None = None) -> MagicMock:
    a = MagicMock()
    a.source_kind = kind
    a.source_name = "test-source"
    a.rate_limit_per_second = 1.0
    a.source_hosts = {"example.com"} if hosts is None else hosts
    return a


class TestSharedStorage:
    """Regression for the worker's `database is locked` spam: building a fresh
    AsyncSqliteStorage (a new SQLite connection) per build() defeated Hishel's
    own write serialisation. The factory must now reuse ONE storage per db_path."""

    def setup_method(self) -> None:
        _SHARED_STORAGE.clear()

    def teardown_method(self) -> None:
        _SHARED_STORAGE.clear()

    def test_shared_storage_is_singleton_per_path(self) -> None:
        settings = _settings()
        first = _shared_storage(settings)
        second = _shared_storage(settings)
        assert first is second  # one connection + one write-lock, not one-per-call

    def test_shared_storage_distinct_per_path(self) -> None:
        assert _shared_storage(_settings("/tmp/a.db")) is not _shared_storage(
            _settings("/tmp/b.db")
        )

    def test_build_reuses_one_storage_across_clients(self) -> None:
        """Two factory builds for the same cache path resolve to ONE shared storage
        (one SQLite connection) — on `main` each build() created its own. Asserted via
        the registry rather than httpx internals; no request is issued, so the storage
        never opens a connection and needs no teardown."""
        settings = _settings()
        assert len(_SHARED_STORAGE) == 0
        HttpClientFactory.build(_adapter(), settings)
        HttpClientFactory.build(_adapter(), settings)
        assert len(_SHARED_STORAGE) == 1

    async def test_client_close_leaves_shared_storage_open(self) -> None:
        """Regression (prod npm 17:01, Oct 2026): Hishel's transport `aclose()`
        closed the SHARED storage, so one cycle finishing (`async with client:`)
        killed every concurrent cycle with `Cannot operate on a closed database`.
        Closing one client must not close the process-shared storage."""
        settings = _settings()
        storage = _shared_storage(settings)
        close_spy = AsyncMock()
        storage.close = close_spy  # type: ignore[method-assign]
        client = HttpClientFactory.build(_adapter(), settings)
        await client.aclose()
        close_spy.assert_not_awaited()


class TestHishelTtlHook:
    """The per-request TTL extension is what lets the shared storage keep each
    adapter's retention (github 24h vs aggregator 1h) per cache entry."""

    @pytest.mark.asyncio
    async def test_hook_sets_request_extension(self) -> None:
        hook = _hishel_ttl_hook(3600.0)
        request = httpx.Request("GET", "https://example.com/feed")
        await hook(request)
        assert request.extensions["caching"] == {"ttl": 3600.0}

    @pytest.mark.asyncio
    async def test_extension_not_sent_as_a_header(self) -> None:
        """An httpx extension is internal — it must never leak onto the wire."""
        hook = _hishel_ttl_hook(86400.0)
        request = httpx.Request("GET", "https://api.github.com/repos/x/y")
        await hook(request)
        assert "x-hishel-ttl" not in {k.lower() for k in request.headers}


class TestRfcRevalidation:
    """Hishel 2.x defaults to a NON-RFC cache; the factory must opt into RFC-9111 so
    a stale entry is revalidated with a conditional GET (a free 304 vs the GitHub
    rate limit) instead of being served blindly or refetched in full."""

    @pytest.mark.asyncio
    async def test_etag_revalidates_with_conditional_get(self, tmp_path: Path) -> None:
        conditional: list[str | None] = []

        def upstream(request: httpx.Request) -> httpx.Response:
            conditional.append(request.headers.get("if-none-match"))
            if request.headers.get("if-none-match") == '"v1"':
                return httpx.Response(304, headers={"etag": '"v1"'})
            return httpx.Response(
                200, headers={"etag": '"v1"', "cache-control": "no-cache"}, content=b"body"
            )

        storage = AsyncSqliteStorage(database_path=f"{tmp_path}/cache.db")
        transport = _SharedStorageCacheTransport(
            next_transport=httpx.MockTransport(upstream),
            storage=storage,
            rfc=CacheOptions(shared=True, allow_stale=True),
        )
        try:
            async with httpx.AsyncClient(
                transport=transport, event_hooks={"request": [_hishel_ttl_hook(60.0)]}
            ) as client:
                first = await client.get("https://example.com/feed")
                second = await client.get("https://example.com/feed")
            assert first.content == second.content == b"body"
            assert second.status_code == 200
            assert first.extensions["caching"]["stored"] is True
            assert second.extensions["caching"]["revalidated"] is True
            assert conditional == [None, '"v1"']
        finally:
            await storage.close()
