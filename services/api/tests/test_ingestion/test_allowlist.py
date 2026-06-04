"""Tests for the reusable SSRF allowlist validator (framework/allowlist.py)."""

from __future__ import annotations

import pytest

from app.ingestion.config.generated.source_registry import ALL_HOSTS
from app.ingestion.framework.allowlist import assert_host_allowed, is_private_ip
from app.ingestion.framework.exceptions import OutboundDenyError


def test_allows_declared_yaml_host() -> None:
    # registry.smithery.ai is declared in smithery.yaml `hosts:` → in ALL_HOSTS.
    assert "registry.smithery.ai" in ALL_HOSTS
    assert_host_allowed("https://registry.smithery.ai/servers?page=1", ALL_HOSTS)
    assert_host_allowed("https://glama.ai/api/mcp/v1/servers", ALL_HOSTS)


def test_rejects_undeclared_host() -> None:
    with pytest.raises(OutboundDenyError, match="OUTBOUND DENY"):
        assert_host_allowed("https://evil.example.com/x", ALL_HOSTS)


def test_rejects_private_ip_even_if_in_allowlist() -> None:
    # A private IP literal must be denied even when the allowlist contains it.
    with pytest.raises(OutboundDenyError, match="private IP"):
        assert_host_allowed("http://127.0.0.1/x", {"127.0.0.1"})
    with pytest.raises(OutboundDenyError, match="private IP"):
        assert_host_allowed("http://169.254.169.254/latest", {"169.254.169.254"})


def test_host_match_is_case_insensitive() -> None:
    assert_host_allowed("https://GLAMA.ai/x", {"glama.ai"})


@pytest.mark.parametrize(
    ("host", "expected"),
    [
        ("127.0.0.1", True),
        ("10.1.2.3", True),
        ("172.16.0.1", True),
        ("192.168.1.1", True),
        ("169.254.1.1", True),
        ("::1", True),
        ("8.8.8.8", False),
        ("glama.ai", False),  # hostname (not an IP literal) → not private
    ],
)
def test_is_private_ip(host: str, expected: bool) -> None:
    assert is_private_ip(host) is expected
