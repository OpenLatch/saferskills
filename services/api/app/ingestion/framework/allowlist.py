"""Reusable outbound host allowlist + private-IP denylist (SSRF guard).

Extracted from `http_client.py::_SSRFTransport` so it is a single source of truth
shared by:
  - the HTTPX transport (`_SSRFTransport`, which delegates here), and
  - the curl_cffi scrape fetches (which bypass the HTTPX transport layer entirely
    and therefore must call `assert_host_allowed` themselves before every request).

The contract mirrors `.claude/rules/security.md` § Public-input handling #2: an
outbound request may only target a host in the per-adapter allowlist (the YAML
`hosts:` list), and never a private/link-local IP literal.
"""

from __future__ import annotations

import ipaddress
from collections.abc import Set as AbstractSet

import httpx

from app.ingestion.framework.exceptions import OutboundDenyError

# Private / link-local / loopback ranges that must never be reached outbound.
_PRIVATE_NETS = (
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("::1/128"),
)


def is_private_ip(host: str) -> bool:
    """True if `host` is a literal IP address inside a private/link-local range.

    A hostname (not an IP literal) returns False — the allowlist gates those.
    """
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return any(ip in net for net in _PRIVATE_NETS)


def assert_host_allowed(url: str, allowed_hosts: AbstractSet[str]) -> None:
    """Raise OutboundDenyError unless `url`'s host is in `allowed_hosts` and is not
    a private IP. Exact (case-insensitive) host membership — never a substring match
    (CodeQL py/incomplete-url-substring-sanitization)."""
    host = (httpx.URL(url).host or "").lower()
    allowlist = {h.lower() for h in allowed_hosts}
    if host not in allowlist:
        raise OutboundDenyError(f"OUTBOUND DENY: {host} not in allowlist {sorted(allowlist)}")
    if is_private_ip(host):
        raise OutboundDenyError(f"SSRF DENY: private IP {host}")
