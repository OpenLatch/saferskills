"""Tests for app.core.access_log_middleware redact_ip and classify_action."""

from __future__ import annotations

import pytest

from app.core.access_log_middleware import classify_action, redact_ip

# ---------------------------------------------------------------------------
# redact_ip
# ---------------------------------------------------------------------------


class TestRedactIp:
    @pytest.mark.parametrize(
        "raw, expected",
        [
            ("192.168.1.255", "192.168.1.0"),
            ("10.0.0.1", "10.0.0.0"),
            ("172.16.200.5", "172.16.200.0"),
            ("8.8.8.8", "8.8.8.0"),
            ("1.2.3.4", "1.2.3.0"),
        ],
    )
    def test_v4_masked_to_slash_24(self, raw: str, expected: str) -> None:
        assert redact_ip(raw) == expected

    @pytest.mark.parametrize(
        "raw, expected",
        [
            ("2001:db8:abcd:1234::1", "2001:db8:abcd::"),
            ("fe80::1", "fe80::"),
            ("::1", "::"),
        ],
    )
    def test_v6_masked_to_slash_48(self, raw: str, expected: str) -> None:
        result = redact_ip(raw)
        # The network address for /48 should be a valid IPv6 string
        assert result is not None
        import ipaddress

        net = ipaddress.ip_network(f"{raw}/48", strict=False)
        assert result == str(net.network_address)

    def test_none_returns_none(self) -> None:
        assert redact_ip(None) is None

    def test_empty_string_returns_none(self) -> None:
        assert redact_ip("") is None

    def test_junk_string_returns_none(self) -> None:
        assert redact_ip("not-an-ip") is None

    def test_localhost_masked(self) -> None:
        result = redact_ip("127.0.0.1")
        assert result == "127.0.0.0"


# ---------------------------------------------------------------------------
# classify_action
# ---------------------------------------------------------------------------


class TestClassifyAction:
    def test_get_items_no_query_returns_catalog_filter(self) -> None:
        assert classify_action("GET", "/api/v1/items", False) == "catalog_filter"

    def test_get_items_trailing_slash_no_query(self) -> None:
        assert classify_action("GET", "/api/v1/items/", False) == "catalog_filter"

    def test_get_items_with_query_returns_catalog_search(self) -> None:
        assert classify_action("GET", "/api/v1/items", True) == "catalog_search"

    def test_get_item_slug_returns_item_view(self) -> None:
        assert classify_action("GET", "/api/v1/items/acme--my-skill", False) == "item_view"

    def test_get_item_slug_with_query_still_item_view(self) -> None:
        assert classify_action("GET", "/api/v1/items/acme--my-skill", True) == "item_view"

    def test_get_facets_returns_none(self) -> None:
        assert classify_action("GET", "/api/v1/items/facets", False) is None

    def test_get_item_subresource_returns_none(self) -> None:
        # e.g. /api/v1/items/acme--skill/download — has a slash after the slug
        assert classify_action("GET", "/api/v1/items/acme--skill/download", False) is None

    def test_post_items_returns_none(self) -> None:
        assert classify_action("POST", "/api/v1/items", False) is None

    def test_unrelated_path_returns_none(self) -> None:
        assert classify_action("GET", "/api/v1/health", False) is None

    def test_delete_returns_none(self) -> None:
        assert classify_action("DELETE", "/api/v1/items/slug", False) is None
