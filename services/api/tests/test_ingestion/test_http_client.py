"""Tests for app.ingestion.framework.http_client._SSRFTransport + shared cache storage."""

from __future__ import annotations

from unittest.mock import MagicMock

import httpx
import pytest

from app.ingestion.framework import http_client
from app.ingestion.framework.exceptions import OutboundDenyError
from app.ingestion.framework.http_client import (
    HttpClientFactory,
    _hishel_ttl_hook,  # pyright: ignore[reportPrivateUsage]
    _shared_storage,  # pyright: ignore[reportPrivateUsage]
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
        http_client._SHARED_STORAGE.clear()

    def teardown_method(self) -> None:
        http_client._SHARED_STORAGE.clear()

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
        """Two clients built from the factory share the SAME cache storage object —
        on `main` each build() created a new one (the bug). No request is issued,
        so the storage never opens a connection and needs no teardown."""
        settings = _settings()
        c1 = HttpClientFactory.build(_adapter(), settings)
        c2 = HttpClientFactory.build(_adapter(), settings)
        assert c1._transport.storage is c2._transport.storage  # pyright: ignore[reportAttributeAccessIssue]


class TestHishelTtlHook:
    """The per-request TTL extension is what lets the shared storage keep each
    adapter's retention (github 24h vs aggregator 1h) per cache entry."""

    @pytest.mark.asyncio
    async def test_hook_sets_request_extension(self) -> None:
        hook = _hishel_ttl_hook(3600.0)
        request = httpx.Request("GET", "https://example.com/feed")
        await hook(request)
        assert request.extensions["hishel_ttl"] == 3600.0

    @pytest.mark.asyncio
    async def test_extension_not_sent_as_a_header(self) -> None:
        """An httpx extension is internal — it must never leak onto the wire."""
        hook = _hishel_ttl_hook(86400.0)
        request = httpx.Request("GET", "https://api.github.com/repos/x/y")
        await hook(request)
        assert "x-hishel-ttl" not in {k.lower() for k in request.headers}
