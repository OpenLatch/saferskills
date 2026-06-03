"""Regression tests for the scan-submit rate-limit loopback exemption.

The public `POST /api/v1/scans` per-IP daily cap (D-FE-11) is an anti-abuse
control for anonymous submissions. Trusted local seeding (the data-seed CLI)
connects over loopback and must be exempt — otherwise the fixture corpus blows
past the 10/day budget. These tests pin the security boundary: loopback is
exempt, every routable / Fly-6PN source is not.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import cast

from fastapi import Request

from app.core.config import Settings
from app.routers.scans import (
    _is_loopback,  # pyright: ignore[reportPrivateUsage]
    _peer_host,  # pyright: ignore[reportPrivateUsage]
    _rate_limit_ip,  # pyright: ignore[reportPrivateUsage]
)


def _fake_request(peer: str | None, headers: dict[str, str] | None = None) -> Request:
    """Minimal Request stand-in exposing `.client.host` + `.headers.get`."""
    client = SimpleNamespace(host=peer) if peer is not None else None
    header_map = {k.lower(): v for k, v in (headers or {}).items()}
    return cast(
        Request,
        SimpleNamespace(client=client, headers=SimpleNamespace(get=header_map.get)),
    )


def test_loopback_v4_is_exempt() -> None:
    assert _is_loopback("127.0.0.1") is True
    # Whole 127.0.0.0/8 block, not just .1.
    assert _is_loopback("127.0.0.53") is True


def test_loopback_v6_is_exempt() -> None:
    assert _is_loopback("::1") is True


def test_public_and_private_sources_are_not_exempt() -> None:
    # Routable public IP — a real anonymous submitter.
    assert _is_loopback("203.0.113.7") is False
    # Fly 6PN private network — how public traffic reaches the app behind the
    # Fly proxy. Must still be rate-limited.
    assert _is_loopback("fdaa:0:1::3") is False
    # LAN address — not loopback.
    assert _is_loopback("192.168.1.10") is False


def test_unparseable_host_is_not_exempt() -> None:
    # `request.client.host` can be missing ("unknown") or a non-IP peer label;
    # fail closed — rate-limit it.
    assert _is_loopback("unknown") is False
    assert _is_loopback("") is False


def test_peer_host_reads_tcp_peer() -> None:
    assert _peer_host(_fake_request("203.0.113.7")) == "203.0.113.7"
    # Missing client → the fail-closed sentinel (never loopback).
    assert _peer_host(_fake_request(None)) == "unknown"


def test_rate_limit_ip_ignores_xff_when_no_secret_configured() -> None:
    # Default posture (no proxy secret): the bucket keys on the raw peer, XFF is
    # never consulted — so a direct caller cannot spoof their bucket.
    settings = Settings(saferskills_proxy_shared_secret=None)
    req = _fake_request("198.51.100.4", {"X-Forwarded-For": "1.2.3.4"})
    assert _rate_limit_ip(req, settings) == "198.51.100.4"


def test_rate_limit_ip_uses_leftmost_xff_on_secret_match() -> None:
    # The proxy proves itself with the shared secret → the visitor is the
    # left-most XFF entry it preserved (the rest is the proxy chain).
    settings = Settings(saferskills_proxy_shared_secret="s3cret")
    req = _fake_request(
        "fdaa:0:1::3",
        {"X-Forwarded-For": "203.0.113.7, fdaa:0:1::3", "X-Proxy-Secret": "s3cret"},
    )
    assert _rate_limit_ip(req, settings) == "203.0.113.7"


def test_rate_limit_ip_ignores_xff_on_secret_mismatch() -> None:
    # A direct caller forging XFF but without the (unguessable) secret is NOT
    # trusted — it falls back to its real peer. This is the anti-spoof boundary.
    settings = Settings(saferskills_proxy_shared_secret="s3cret")
    req = _fake_request(
        "203.0.113.7",
        {"X-Forwarded-For": "1.2.3.4", "X-Proxy-Secret": "wrong"},
    )
    assert _rate_limit_ip(req, settings) == "203.0.113.7"
    # Missing secret header entirely → also the peer.
    no_header = _fake_request("203.0.113.7", {"X-Forwarded-For": "1.2.3.4"})
    assert _rate_limit_ip(no_header, settings) == "203.0.113.7"


def test_rate_limit_ip_falls_back_to_peer_without_xff() -> None:
    # Secret matches but no XFF present → the peer, not a crash.
    settings = Settings(saferskills_proxy_shared_secret="s3cret")
    req = _fake_request("198.51.100.4", {"X-Proxy-Secret": "s3cret"})
    assert _rate_limit_ip(req, settings) == "198.51.100.4"


def test_loopback_exemption_keys_on_peer_not_spoofable_xff() -> None:
    # The exemption is computed from the peer, so a remote caller forging
    # `X-Forwarded-For: 127.0.0.1` is NOT exempted — its peer is still public.
    req = _fake_request("203.0.113.7", {"X-Forwarded-For": "127.0.0.1"})
    assert _is_loopback(_peer_host(req)) is False
