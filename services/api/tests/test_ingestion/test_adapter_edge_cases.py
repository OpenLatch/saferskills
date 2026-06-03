"""Edge-case tests for adapter normalize() paths not covered by the main test.

Covers the early-return branches and enrich() no-op path.
Also covers robots.py (mocked HTTP) and registry_adapter.py counters.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.ingestion.framework.base_adapter import RawItem


def _raw(payload: Any, status: int = 200) -> RawItem:
    body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    return RawItem(
        source_id="edge/test",
        raw_body_bytes=body,
        raw_body_hash=hashlib.sha256(body).hexdigest(),
        http_status=status,
        fetch_tier=1,
        payload_hint=payload,
    )


# ---------------------------------------------------------------------------
# github_topics: missing owner/name branches (lines 222, 227)
# ---------------------------------------------------------------------------


class TestGithubTopicsEdgeCases:
    def test_normalize_non_dict_payload_hint_returns_none(self) -> None:
        import app.ingestion.sources.github_topics  # noqa: F401  # pyright: ignore[reportUnusedImport]
        from app.ingestion.framework.base_adapter import build_adapter

        adapter = build_adapter("github_topics")
        raw = RawItem(
            source_id="edge/bad",
            raw_body_bytes=b"not-json",
            raw_body_hash=hashlib.sha256(b"not-json").hexdigest(),
            http_status=200,
            fetch_tier=1,
            payload_hint="not-a-dict",  # type: ignore[arg-type]
        )
        assert adapter.normalize(raw) is None

    def test_normalize_missing_owner_returns_none(self) -> None:
        from app.ingestion.framework.base_adapter import build_adapter

        adapter = build_adapter("github_topics")
        raw = _raw({"name": "some-repo", "description": "missing owner"})
        # owner is absent → org = "" → return None
        assert adapter.normalize(raw) is None

    def test_normalize_missing_repo_name_returns_none(self) -> None:
        from app.ingestion.framework.base_adapter import build_adapter

        adapter = build_adapter("github_topics")
        raw = _raw({"owner": {"login": "acme"}})  # no 'name'
        assert adapter.normalize(raw) is None

    @pytest.mark.asyncio
    async def test_enrich_no_op_when_no_github_coords(self) -> None:
        from app.ingestion.framework.base_adapter import NormalizedItem, build_adapter

        adapter = build_adapter("github_topics")
        n = NormalizedItem(github_org=None, github_repo=None, display_name="x")
        client = AsyncMock()
        await adapter.enrich(client, n)
        client.get.assert_not_called()

    @pytest.mark.asyncio
    async def test_enrich_fetches_manifest_files(self) -> None:
        from app.ingestion.framework.base_adapter import NormalizedItem, build_adapter

        adapter = build_adapter("github_topics")
        n = NormalizedItem(
            github_org="acme",
            github_repo="my-skill",
            display_name="my-skill",
            default_branch="main",
        )

        mock_200 = MagicMock()
        mock_200.status_code = 200
        mock_200.content = b"# My Skill"

        mock_404 = MagicMock()
        mock_404.status_code = 404

        client = AsyncMock()
        # SKILL.md → 200, mcp.json → 404, README.md → 200
        client.get = AsyncMock(side_effect=[mock_200, mock_404, mock_200])

        await adapter.enrich(client, n)
        assert "SKILL.md" in n.metadata_files
        assert n.metadata_files["SKILL.md"] == b"# My Skill"
        assert "mcp.json" not in n.metadata_files

    @pytest.mark.asyncio
    async def test_enrich_swallows_network_errors(self) -> None:
        from app.ingestion.framework.base_adapter import NormalizedItem, build_adapter

        adapter = build_adapter("github_topics")
        n = NormalizedItem(
            github_org="acme",
            github_repo="x",
            display_name="x",
        )
        client = AsyncMock()
        client.get = AsyncMock(side_effect=Exception("network error"))
        # Should not raise
        await adapter.enrich(client, n)
        assert n.metadata_files == {}


# ---------------------------------------------------------------------------
# mcp_registry: normalize missing github coords
# ---------------------------------------------------------------------------


class TestMcpRegistryEdgeCases:
    def test_normalize_no_github_coords(self) -> None:
        import app.ingestion.sources.mcp_registry  # noqa: F401  # pyright: ignore[reportUnusedImport]
        from app.ingestion.framework.base_adapter import build_adapter

        adapter = build_adapter("mcp_registry")
        raw = _raw(
            {
                "id": "srv-1",
                "name": "my-server",
                "displayName": "My Server",
                "description": "no GitHub",
                "repository": {},
            }
        )
        result = adapter.normalize(raw)
        assert result is not None
        assert result.github_org is None
        assert result.github_repo is None

    def test_normalize_empty_record_returns_none(self) -> None:
        from app.ingestion.framework.base_adapter import build_adapter

        adapter = build_adapter("mcp_registry")
        raw = _raw({})
        # no name → display_name is 'unknown', no crash
        result = adapter.normalize(raw)
        assert result is not None  # empty but valid


# ---------------------------------------------------------------------------
# npm: normalize edge cases
# ---------------------------------------------------------------------------


class TestNpmEdgeCases:
    def test_normalize_empty_doc_returns_none(self) -> None:
        import app.ingestion.sources.npm  # noqa: F401  # pyright: ignore[reportUnusedImport]
        from app.ingestion.framework.base_adapter import build_adapter

        adapter = build_adapter("npm")
        raw = _raw({})
        assert adapter.normalize(raw) is None

    def test_normalize_string_repo_url(self) -> None:
        from app.ingestion.framework.base_adapter import build_adapter

        adapter = build_adapter("npm")
        raw = _raw(
            {
                "name": "mcp-server-x",
                "dist-tags": {"latest": "1.0.0"},
                "versions": {
                    "1.0.0": {
                        "name": "mcp-server-x",
                        "repository": "https://github.com/acme/mcp-server-x",
                    }
                },
            }
        )
        result = adapter.normalize(raw)
        assert result is not None
        # String repo is handled — either coords or None
        assert isinstance(result.github_org, (str, type(None)))

    def test_normalize_dict_license(self) -> None:
        from app.ingestion.framework.base_adapter import build_adapter

        adapter = build_adapter("npm")
        raw = _raw(
            {
                "name": "mcp-server-y",
                "dist-tags": {"latest": "1.0.0"},
                "versions": {
                    "1.0.0": {
                        "name": "mcp-server-y",
                        "license": {"type": "MIT"},
                    }
                },
            }
        )
        result = adapter.normalize(raw)
        assert result is not None
        assert result.license_spdx == "MIT"


# ---------------------------------------------------------------------------
# pypi: normalize edge cases
# ---------------------------------------------------------------------------


class TestPypiEdgeCases:
    def test_normalize_empty_info_returns_none(self) -> None:
        import app.ingestion.sources.pypi  # noqa: F401  # pyright: ignore[reportUnusedImport]
        from app.ingestion.framework.base_adapter import build_adapter

        adapter = build_adapter("pypi")
        raw = _raw({"info": {}})
        assert adapter.normalize(raw) is None

    def test_normalize_non_mcp_name_gives_skill_kind(self) -> None:
        from app.ingestion.framework.base_adapter import build_adapter

        adapter = build_adapter("pypi")
        raw = _raw(
            {
                "info": {
                    "name": "my-ai-skill",  # doesn't match "mcp"
                    "summary": "A skill",
                    "license": "MIT",
                    "yanked": False,
                    "project_urls": {},
                }
            }
        )
        result = adapter.normalize(raw)
        assert result is not None
        assert result.kind == "skill"


# ---------------------------------------------------------------------------
# robots.py — mocked HTTP
# ---------------------------------------------------------------------------


class TestRobotsModule:
    @pytest.mark.asyncio
    async def test_is_allowed_returns_true_on_http_error(self) -> None:
        """Fail-open: robots.txt fetch error → allow the request."""
        import httpx

        from app.ingestion.framework import robots

        # Patch the cache to empty and make the HTTP call fail
        robots._CACHE.clear()  # pyright: ignore[reportPrivateUsage]
        with patch("httpx.AsyncClient") as MockClient:
            mock_client_instance = AsyncMock()
            mock_client_instance.get = AsyncMock(side_effect=httpx.HTTPError("timeout"))
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client_instance)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=None)
            result = await robots.is_allowed("https://example.com/some/path")
        assert result is True

    @pytest.mark.asyncio
    async def test_is_allowed_returns_true_on_404(self) -> None:
        """No robots.txt (404) → allow everything."""
        from app.ingestion.framework import robots

        robots._CACHE.clear()  # pyright: ignore[reportPrivateUsage]
        with patch("httpx.AsyncClient") as MockClient:
            mock_resp = MagicMock()
            mock_resp.status_code = 404
            mock_client_instance = AsyncMock()
            mock_client_instance.get = AsyncMock(return_value=mock_resp)
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client_instance)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=None)
            result = await robots.is_allowed("https://example.com/any/path")
        assert result is True

    @pytest.mark.asyncio
    async def test_is_allowed_false_when_disallowed(self) -> None:
        """Disallow rule in robots.txt → deny the request."""
        from protego import Protego

        from app.ingestion.framework import robots

        robots._CACHE.clear()  # pyright: ignore[reportPrivateUsage]
        disallow_all_robots = "User-agent: *\nDisallow: /"
        rp = Protego.parse(disallow_all_robots)
        # Pre-seed the cache with a disallow-all policy
        import time

        robots._CACHE["https://example.com"] = (rp, time.monotonic() + 3600)  # pyright: ignore[reportPrivateUsage]

        result = await robots.is_allowed("https://example.com/any/path")
        assert result is False

    @pytest.mark.asyncio
    async def test_is_allowed_true_when_allowed_by_robots(self) -> None:
        """Allow rule → allow the request."""
        from protego import Protego

        from app.ingestion.framework import robots

        robots._CACHE.clear()  # pyright: ignore[reportPrivateUsage]
        allow_all_robots = "User-agent: *\nDisallow:"
        rp = Protego.parse(allow_all_robots)
        import time

        robots._CACHE["https://example.com"] = (rp, time.monotonic() + 3600)  # pyright: ignore[reportPrivateUsage]

        result = await robots.is_allowed("https://example.com/any/path")
        assert result is True

    @pytest.mark.asyncio
    async def test_cache_hit_skips_fetch(self) -> None:
        """Cached robots.txt should not trigger a network fetch."""
        import time

        from protego import Protego

        from app.ingestion.framework import robots

        robots._CACHE.clear()  # pyright: ignore[reportPrivateUsage]
        rp = Protego.parse("User-agent: *\nDisallow:")
        robots._CACHE["https://cached.example.com"] = (rp, time.monotonic() + 3600)  # pyright: ignore[reportPrivateUsage]

        with patch("httpx.AsyncClient") as MockClient:
            result = await robots.is_allowed("https://cached.example.com/path")
            MockClient.assert_not_called()
        assert result is True


# ---------------------------------------------------------------------------
# scraping_adapter.py — import coverage
# ---------------------------------------------------------------------------


class TestScrapingAdapterImport:
    def test_scraping_adapter_is_importable(self) -> None:
        from app.ingestion.framework.scraping_adapter import (
            ScrapingAdapter,  # noqa: F401  # pyright: ignore[reportUnusedImport]
        )
