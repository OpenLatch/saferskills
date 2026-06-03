"""Tests for app.ingestion.framework.http_client._SSRFTransport."""

from __future__ import annotations

import httpx
import pytest

from app.ingestion.framework.exceptions import OutboundDenyError
from app.ingestion.framework.http_client import (
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
