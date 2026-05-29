"""Regression tests for the scan-submit rate-limit loopback exemption.

The public `POST /api/v1/scans` per-IP daily cap (D-FE-11) is an anti-abuse
control for anonymous submissions. Trusted local seeding (the data-seed CLI)
connects over loopback and must be exempt — otherwise the fixture corpus blows
past the 10/day budget. These tests pin the security boundary: loopback is
exempt, every routable / Fly-6PN source is not.
"""

from __future__ import annotations

from app.routers.scans import _is_loopback  # pyright: ignore[reportPrivateUsage]


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
