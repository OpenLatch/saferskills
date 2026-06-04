"""Tests for adapter .normalize() — no live HTTP, uses RawItem + payload_hint."""

from __future__ import annotations

import hashlib
import json
from typing import Any

# Ensure all adapters are registered by importing their modules.
import app.ingestion.sources.github_topics  # pyright: ignore[reportUnusedImport]
import app.ingestion.sources.mcp_registry  # pyright: ignore[reportUnusedImport]
import app.ingestion.sources.npm  # pyright: ignore[reportUnusedImport]
import app.ingestion.sources.pypi  # noqa: F401  # pyright: ignore[reportUnusedImport]
from app.ingestion.framework.base_adapter import (
    ADAPTER_REGISTRY,
    NormalizedItem,
    RawItem,
    build_adapter,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _raw(payload: dict[str, Any], status: int = 200) -> RawItem:
    body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    return RawItem(
        source_id="test/item",
        raw_body_bytes=body,
        raw_body_hash=hashlib.sha256(body).hexdigest(),
        http_status=status,
        fetch_tier=1,
        payload_hint=payload,
    )


def _github_repo_payload(
    org: str = "acme",
    repo: str = "my-skill",
    stars: int = 5,
    archived: bool = False,
) -> dict[str, Any]:
    return {
        "id": 1,
        "name": repo,
        "full_name": f"{org}/{repo}",
        "owner": {"login": org, "type": "Organization"},
        "html_url": f"https://github.com/{org}/{repo}",
        "description": "A great skill",
        "stargazers_count": stars,
        "pushed_at": "2025-01-01T00:00:00Z",
        "default_branch": "main",
        "archived": archived,
        "license": {"spdx_id": "MIT"},
        "size": 50,
    }


# ---------------------------------------------------------------------------
# Adapter registry smoke test
# ---------------------------------------------------------------------------


class TestAdapterRegistry:
    def test_all_expected_adapters_registered(self) -> None:
        expected = {"github_topics", "mcp_registry", "npm", "pypi"}
        for name in expected:
            assert name in ADAPTER_REGISTRY, f"{name} not in ADAPTER_REGISTRY"

    def test_build_adapter_returns_instance(self) -> None:
        adapter = build_adapter("github_topics")
        assert adapter is not None
        assert adapter.source_name == "github_topics"


# ---------------------------------------------------------------------------
# github_topics normalize
# ---------------------------------------------------------------------------


class TestGithubTopicsNormalize:
    def test_normalize_200_returns_normalized_item(self) -> None:
        adapter = build_adapter("github_topics")
        payload = _github_repo_payload()
        raw = _raw(payload)
        result = adapter.normalize(raw)
        assert result is not None
        assert isinstance(result, NormalizedItem)

    def test_normalize_github_org_and_repo(self) -> None:
        adapter = build_adapter("github_topics")
        raw = _raw(_github_repo_payload(org="testorg", repo="test-repo"))
        result = adapter.normalize(raw)
        assert result is not None
        assert result.github_org == "testorg"
        assert result.github_repo == "test-repo"

    def test_normalize_non_200_returns_none(self) -> None:
        adapter = build_adapter("github_topics")
        raw = _raw(_github_repo_payload(), status=304)
        assert adapter.normalize(raw) is None

    def test_normalize_404_returns_none(self) -> None:
        adapter = build_adapter("github_topics")
        raw = _raw({}, status=404)
        assert adapter.normalize(raw) is None

    def test_normalize_aggregator_listings(self) -> None:
        adapter = build_adapter("github_topics")
        raw = _raw(_github_repo_payload())
        result = adapter.normalize(raw)
        assert result is not None
        assert "github_topics" in result.aggregator_listings

    def test_normalize_license_spdx(self) -> None:
        adapter = build_adapter("github_topics")
        raw = _raw(_github_repo_payload())
        result = adapter.normalize(raw)
        assert result is not None
        assert result.license_spdx == "MIT"

    def test_normalize_stars(self) -> None:
        adapter = build_adapter("github_topics")
        raw = _raw(_github_repo_payload(stars=99))
        result = adapter.normalize(raw)
        assert result is not None
        assert result.stars == 99


# ---------------------------------------------------------------------------
# mcp_registry normalize
# ---------------------------------------------------------------------------


class TestMcpRegistryNormalize:
    def _mcp_record(
        self,
        name: str = "io.github.acme/mcp-tool",
        description: str = "An MCP server",
        github_url: str = "https://github.com/acme/mcp-tool",
    ) -> dict[str, Any]:
        return {
            "id": "server-1",
            "name": name,
            "displayName": "MCP Tool",
            "description": description,
            "repository": {"url": github_url},
        }

    def test_normalize_200_returns_normalized_item(self) -> None:
        adapter = build_adapter("mcp_registry")
        raw = _raw(self._mcp_record())
        result = adapter.normalize(raw)
        assert result is not None
        assert isinstance(result, NormalizedItem)

    def test_normalize_kind_is_mcp_server(self) -> None:
        adapter = build_adapter("mcp_registry")
        raw = _raw(self._mcp_record())
        result = adapter.normalize(raw)
        assert result is not None
        assert result.kind == "mcp_server"

    def test_normalize_parses_github_coords_from_url(self) -> None:
        adapter = build_adapter("mcp_registry")
        raw = _raw(self._mcp_record(github_url="https://github.com/acme/mcp-tool"))
        result = adapter.normalize(raw)
        assert result is not None
        assert result.github_org == "acme"
        assert result.github_repo == "mcp-tool"

    def test_normalize_non_200_returns_none(self) -> None:
        adapter = build_adapter("mcp_registry")
        raw = _raw(self._mcp_record(), status=304)
        assert adapter.normalize(raw) is None

    def test_normalize_aggregator_listings_contains_mcp_registry(self) -> None:
        adapter = build_adapter("mcp_registry")
        raw = _raw(self._mcp_record())
        result = adapter.normalize(raw)
        assert result is not None
        assert "mcp_registry" in result.aggregator_listings


# ---------------------------------------------------------------------------
# npm normalize
# ---------------------------------------------------------------------------


class TestNpmNormalize:
    def _npm_doc(
        self,
        name: str = "mcp-server-acme",
        github_url: str = "https://github.com/acme/mcp-server-acme",
    ) -> dict[str, Any]:
        return {
            "name": name,
            "description": "An npm MCP package",
            "dist-tags": {"latest": "1.0.0"},
            "versions": {
                "1.0.0": {
                    "name": name,
                    "description": "An npm MCP package",
                    "repository": {"type": "git", "url": f"git+{github_url}.git"},
                    "license": "MIT",
                }
            },
        }

    def test_normalize_200_returns_normalized_item(self) -> None:
        adapter = build_adapter("npm")
        raw = _raw(self._npm_doc())
        result = adapter.normalize(raw)
        assert result is not None
        assert isinstance(result, NormalizedItem)

    def test_normalize_kind_is_mcp_server(self) -> None:
        adapter = build_adapter("npm")
        raw = _raw(self._npm_doc(name="mcp-server-acme"))
        result = adapter.normalize(raw)
        assert result is not None
        assert result.kind == "mcp_server"

    def test_normalize_parses_github_coords(self) -> None:
        adapter = build_adapter("npm")
        raw = _raw(self._npm_doc(github_url="https://github.com/acme/mcp-server-acme"))
        result = adapter.normalize(raw)
        assert result is not None
        assert result.github_org == "acme"
        assert result.github_repo == "mcp-server-acme"

    def test_normalize_non_200_returns_none(self) -> None:
        adapter = build_adapter("npm")
        raw = _raw(self._npm_doc(), status=404)
        assert adapter.normalize(raw) is None

    def test_normalize_aggregator_listings_contains_npm(self) -> None:
        adapter = build_adapter("npm")
        raw = _raw(self._npm_doc())
        result = adapter.normalize(raw)
        assert result is not None
        assert "npm" in result.aggregator_listings


# ---------------------------------------------------------------------------
# pypi normalize
# ---------------------------------------------------------------------------


class TestPypiNormalize:
    def _pypi_payload(
        self,
        name: str = "mcp-server-acme",
        github_url: str = "https://github.com/acme/mcp-server-acme",
    ) -> dict[str, Any]:
        return {
            "info": {
                "name": name,
                "summary": "A PyPI MCP package",
                "license": "MIT",
                "yanked": False,
                "project_urls": {"Source": github_url},
            },
            "releases": {},
            "urls": [],
        }

    def test_normalize_200_returns_normalized_item(self) -> None:
        adapter = build_adapter("pypi")
        raw = _raw(self._pypi_payload())
        result = adapter.normalize(raw)
        assert result is not None
        assert isinstance(result, NormalizedItem)

    def test_normalize_kind_mcp_server_for_mcp_name(self) -> None:
        adapter = build_adapter("pypi")
        raw = _raw(self._pypi_payload(name="mcp-server-acme"))
        result = adapter.normalize(raw)
        assert result is not None
        assert result.kind == "mcp_server"

    def test_normalize_parses_github_coords(self) -> None:
        adapter = build_adapter("pypi")
        raw = _raw(self._pypi_payload(github_url="https://github.com/acme/mcp-server-acme"))
        result = adapter.normalize(raw)
        assert result is not None
        assert result.github_org == "acme"
        assert result.github_repo == "mcp-server-acme"

    def test_normalize_rejects_spoofed_github_host(self) -> None:
        """Regression (CodeQL py/incomplete-url-substring-sanitization): a
        publisher-controlled project_url whose host merely CONTAINS 'github.com'
        (e.g. github.com.evil.com) must NOT be treated as a GitHub repo."""
        adapter = build_adapter("pypi")
        for spoof in (
            "https://github.com.evil.com/acme/pkg",
            "https://evilgithub.com/acme/pkg",
            "https://example.com/?redirect=github.com/acme/pkg",
        ):
            raw = _raw(self._pypi_payload(github_url=spoof))
            result = adapter.normalize(raw)
            assert result is not None
            assert result.github_org is None, f"spoofed host accepted: {spoof}"
            assert result.github_repo is None
            assert result.github_url is None

    def test_normalize_non_200_returns_none(self) -> None:
        adapter = build_adapter("pypi")
        raw = _raw(self._pypi_payload(), status=304)
        assert adapter.normalize(raw) is None

    def test_normalize_aggregator_listings_contains_pypi(self) -> None:
        adapter = build_adapter("pypi")
        raw = _raw(self._pypi_payload())
        result = adapter.normalize(raw)
        assert result is not None
        assert "pypi" in result.aggregator_listings

    def test_normalize_yanked_sets_repo_yanked(self) -> None:
        adapter = build_adapter("pypi")
        payload = self._pypi_payload()
        payload["info"]["yanked"] = True
        raw = _raw(payload)
        result = adapter.normalize(raw)
        assert result is not None
        assert result.repo_yanked is True

    def test_normalize_full_text_license_resolved_to_short_spdx(self) -> None:
        """Regression: PyPI's free-form `license` often holds the ENTIRE license body
        (~1.2 KB). It must resolve to a short SPDX id from the trove classifier, never
        the verbatim text (which overflows license_spdx VARCHAR(100) and crashes the
        cycle)."""
        adapter = build_adapter("pypi")
        payload = self._pypi_payload()
        payload["info"]["license"] = "MIT License\n\nCopyright (c) 2026 Acme\n" + ("x " * 600)
        payload["info"]["classifiers"] = ["License :: OSI Approved :: MIT License"]
        result = adapter.normalize(raw=_raw(payload))
        assert result is not None
        assert result.license_spdx == "MIT"
        assert len(result.license_spdx) <= 100

    def test_normalize_prefers_license_expression(self) -> None:
        adapter = build_adapter("pypi")
        payload = self._pypi_payload()
        payload["info"]["license_expression"] = "Apache-2.0"
        payload["info"]["license"] = "full apache text " * 100
        result = adapter.normalize(raw=_raw(payload))
        assert result is not None
        assert result.license_spdx == "Apache-2.0"
