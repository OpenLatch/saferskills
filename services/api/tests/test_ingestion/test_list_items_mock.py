"""Mock-HTTP tests for adapter list_items methods — no live requests."""

from __future__ import annotations

import asyncio
import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.ingestion.config.loader import SourceConfig


def _make_response(data: Any, status: int = 200) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status
    body = json.dumps(data, sort_keys=True, separators=(",", ":")).encode()
    resp.content = body
    resp.json = lambda: data
    resp.headers = {}
    return resp


def _github_topics_config() -> SourceConfig:
    return SourceConfig(
        name="github_topics",
        kind="api",
        hosts=["api.github.com", "raw.githubusercontent.com"],
        discovery={
            "topics": ["claude-skills"],
            "star_shards": ["stars:>0"],
            "code_search_queries": [],
        },
    )


def _mcp_config() -> SourceConfig:
    return SourceConfig(
        name="mcp_registry",
        kind="api",
        hosts=["registry.modelcontextprotocol.io"],
        discovery={"api_base": "https://registry.modelcontextprotocol.io"},
    )


# ---------------------------------------------------------------------------
# github_topics list_items — mocked HTTP
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_github_topics_list_items_200_yields_raw_items() -> None:
    """list_items should yield one RawItem per repo in the search result."""
    from app.ingestion.sources.github_topics import GithubTopicsAdapter

    adapter = GithubTopicsAdapter(_github_topics_config())
    search_result = {
        "total_count": 1,
        "items": [
            {
                "full_name": "acme/my-skill",
                "name": "my-skill",
                "owner": {"login": "acme"},
                "html_url": "https://github.com/acme/my-skill",
                "description": "a skill",
                "stargazers_count": 5,
                "pushed_at": "2025-01-01T00:00:00Z",
                "default_branch": "main",
                "archived": False,
                "license": {"spdx_id": "MIT"},
                "size": 10,
            }
        ],
    }

    client = AsyncMock()
    client.get = AsyncMock(return_value=_make_response(search_result))

    with patch("app.core.config.get_settings") as mock_settings:
        mock_settings.return_value.ingestion_github_code_search_enabled = False
        items = [item async for item in adapter.list_items(client)]

    assert len(items) == 1
    assert items[0].source_id == "acme/my-skill"
    assert items[0].http_status == 200


@pytest.mark.asyncio
async def test_github_topics_list_items_304_yields_304_raw_item() -> None:
    from app.ingestion.sources.github_topics import GithubTopicsAdapter

    adapter = GithubTopicsAdapter(_github_topics_config())

    resp_304 = MagicMock()
    resp_304.status_code = 304
    resp_304.headers = {"etag": '"abc123"'}

    client = AsyncMock()
    client.get = AsyncMock(return_value=resp_304)

    with patch("app.core.config.get_settings") as mock_settings:
        mock_settings.return_value.ingestion_github_code_search_enabled = False
        items = [item async for item in adapter.list_items(client)]

    assert any(item.http_status == 304 for item in items)


@pytest.mark.asyncio
async def test_github_topics_list_items_404_yields_error_item() -> None:
    from app.ingestion.sources.github_topics import GithubTopicsAdapter

    adapter = GithubTopicsAdapter(_github_topics_config())

    resp_404 = _make_response({"message": "Not Found"}, status=404)
    client = AsyncMock()
    client.get = AsyncMock(return_value=resp_404)

    with patch("app.core.config.get_settings") as mock_settings:
        mock_settings.return_value.ingestion_github_code_search_enabled = False
        items = [item async for item in adapter.list_items(client)]

    assert any(item.http_status == 404 for item in items)


@pytest.mark.asyncio
async def test_github_topics_list_items_empty_result_stops() -> None:
    from app.ingestion.sources.github_topics import GithubTopicsAdapter

    adapter = GithubTopicsAdapter(_github_topics_config())
    empty_result: dict[str, object] = {"total_count": 0, "items": []}

    client = AsyncMock()
    client.get = AsyncMock(return_value=_make_response(empty_result))

    with patch("app.core.config.get_settings") as mock_settings:
        mock_settings.return_value.ingestion_github_code_search_enabled = False
        items = [item async for item in adapter.list_items(client)]

    assert len(items) == 0


@pytest.mark.asyncio
async def test_github_topics_list_items_rate_limit_yields_error() -> None:
    from app.ingestion.sources.github_topics import GithubTopicsAdapter

    adapter = GithubTopicsAdapter(_github_topics_config())
    resp_429 = _make_response({"message": "rate limited"}, status=429)

    client = AsyncMock()
    client.get = AsyncMock(return_value=resp_429)

    with patch("app.core.config.get_settings") as mock_settings:
        mock_settings.return_value.ingestion_github_code_search_enabled = False
        items = [item async for item in adapter.list_items(client)]

    assert any(item.error_reason == "rate_limit" for item in items)


# ---------------------------------------------------------------------------
# mcp_registry list_items — mocked DB cursor + HTTP
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mcp_registry_list_items_200_yields_items() -> None:
    from app.ingestion.sources.mcp_registry import McpRegistryAdapter

    adapter = McpRegistryAdapter(_mcp_config())

    # The live /v0/servers feed wraps each entry under `server` with `_meta`
    # bookkeeping siblings; pagination lives under `metadata.nextCursor`.
    server_data = {
        "servers": [
            {
                "server": {
                    "name": "io.github.acme/mcp-tool",
                    "title": "MCP Tool",
                    "description": "An MCP server",
                    "repository": {"url": "https://github.com/acme/mcp-tool"},
                },
                "_meta": {
                    "io.modelcontextprotocol.registry/official": {
                        "updatedAt": "2025-01-01T00:00:00Z",
                        "isLatest": True,
                    }
                },
            }
        ],
        "metadata": {"nextCursor": None},
    }

    resp = _make_response(server_data)
    client = AsyncMock()
    client.get = AsyncMock(return_value=resp)

    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)
    mock_session.commit = AsyncMock()

    with (
        patch("app.db.session.AsyncSessionLocal", return_value=mock_session),
        patch(
            "app.ingestion.framework.cursor.read_cursor",
            AsyncMock(return_value={}),
        ),
        patch("app.ingestion.framework.cursor.write_cursor", AsyncMock()),
    ):
        items = [item async for item in adapter.list_items(client)]

    assert len(items) == 1
    # source_id keys on the stable server name (no per-server id is exposed).
    assert items[0].source_id == "mcp_registry/io.github.acme/mcp-tool"


@pytest.mark.asyncio
async def test_mcp_registry_list_items_304_breaks_loop() -> None:
    from app.ingestion.sources.mcp_registry import McpRegistryAdapter

    adapter = McpRegistryAdapter(_mcp_config())
    resp_304 = MagicMock()
    resp_304.status_code = 304
    resp_304.headers = {}

    client = AsyncMock()
    client.get = AsyncMock(return_value=resp_304)

    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)
    mock_session.commit = AsyncMock()

    with (
        patch("app.db.session.AsyncSessionLocal", return_value=mock_session),
        patch(
            "app.ingestion.framework.cursor.read_cursor",
            AsyncMock(return_value={}),
        ),
        patch("app.ingestion.framework.cursor.write_cursor", AsyncMock()),
    ):
        items = [item async for item in adapter.list_items(client)]

    assert any(item.http_status == 304 for item in items)


@pytest.mark.asyncio
async def test_mcp_registry_checkpoints_each_page_and_resumes_on_error() -> None:
    """Regression: an interrupted full-feed sweep must checkpoint the resume cursor
    per page and NOT advance the watermark / mark success on a transport error.

    Before the fix the cursor was written only at the end of a complete sweep, so a
    5xx (or --reload abort) mid-crawl lost all progress and the next cycle re-crawled
    from the epoch forever (the never-completing zombie loop).
    """
    from app.ingestion.sources.mcp_registry import McpRegistryAdapter

    adapter = McpRegistryAdapter(_mcp_config())

    # Resume from a saved page cursor "cursorA"; page 1 returns nextCursor "cursorB";
    # page 2 fails with a 500 — the sweep is interrupted, not completed.
    page1 = _make_response(
        {
            "servers": [
                {
                    "server": {
                        "name": "io.github.acme/one",
                        "repository": {"url": "https://github.com/acme/one"},
                    },
                    "_meta": {
                        "io.modelcontextprotocol.registry/official": {
                            "updatedAt": "2025-02-02T00:00:00Z",
                            "isLatest": True,
                        }
                    },
                }
            ],
            "metadata": {"nextCursor": "cursorB"},
        }
    )
    page2_err = _make_response({"message": "boom"}, status=500)

    client = AsyncMock()
    client.get = AsyncMock(side_effect=[page1, page2_err])

    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)
    mock_session.commit = AsyncMock()

    save_progress = AsyncMock()
    write_cursor = AsyncMock()
    with (
        patch("app.db.session.AsyncSessionLocal", return_value=mock_session),
        patch(
            "app.ingestion.framework.cursor.read_cursor",
            AsyncMock(
                return_value={"updated_since": "2025-01-01T00:00:00Z", "next_cursor": "cursorA"}
            ),
        ),
        patch("app.ingestion.framework.cursor.save_cursor_progress", save_progress),
        patch("app.ingestion.framework.cursor.write_cursor", write_cursor),
    ):
        items = [item async for item in adapter.list_items(client)]

    # One real server + one error item.
    assert any(it.http_status == 500 for it in items)
    # Checkpoint written BEFORE each page fetch — first the resume point, then the next page.
    checkpoint_cursors = [call.args[2]["next_cursor"] for call in save_progress.await_args_list]
    assert checkpoint_cursors == ["cursorA", "cursorB"]
    # The watermark must NOT advance (updated_since preserved on every checkpoint)...
    assert all(
        call.args[2]["updated_since"] == "2025-01-01T00:00:00Z"
        for call in save_progress.await_args_list
    )
    # ...and the completion write (success=True) must NOT fire on an interrupted sweep.
    write_cursor.assert_not_awaited()


@pytest.mark.asyncio
async def test_mcp_registry_completed_sweep_advances_watermark() -> None:
    """A fully-drained feed advances the watermark + marks the cycle successful."""
    from app.ingestion.sources.mcp_registry import McpRegistryAdapter

    adapter = McpRegistryAdapter(_mcp_config())
    page = _make_response(
        {
            "servers": [
                {
                    "server": {
                        "name": "io.github.acme/done",
                        "repository": {"url": "https://github.com/acme/done"},
                    },
                    "_meta": {
                        "io.modelcontextprotocol.registry/official": {
                            "updatedAt": "2025-03-03T00:00:00Z",
                            "isLatest": True,
                        }
                    },
                }
            ],
            "metadata": {"nextCursor": None},
        }
    )
    client = AsyncMock()
    client.get = AsyncMock(return_value=page)

    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)
    mock_session.commit = AsyncMock()

    write_cursor = AsyncMock()
    with (
        patch("app.db.session.AsyncSessionLocal", return_value=mock_session),
        patch("app.ingestion.framework.cursor.read_cursor", AsyncMock(return_value={})),
        patch("app.ingestion.framework.cursor.save_cursor_progress", AsyncMock()),
        patch("app.ingestion.framework.cursor.write_cursor", write_cursor),
    ):
        _ = [item async for item in adapter.list_items(client)]

    write_cursor.assert_awaited_once()
    # `await_args` is mock introspection (`_Call | None`); type as Any so the
    # positional-arg indexing isn't fought by the fixed-length tuple stub.
    await_args: Any = write_cursor.await_args
    assert await_args is not None
    final_value = await_args.args[3] if len(await_args.args) > 3 else await_args.args[2]
    assert final_value["next_cursor"] is None
    assert final_value["updated_since"] == "2025-03-03T00:00:00Z"
    assert await_args.kwargs.get("success") is True


# ---------------------------------------------------------------------------
# npm search-API list_items — enumerate (search) then fetch (packument), with the
# terminal cursor write on EVERY exit path
# ---------------------------------------------------------------------------


def _npm_config() -> SourceConfig:
    return SourceConfig(
        name="npm",
        kind="api",
        hosts=["registry.npmjs.org", "api.npmjs.org"],
        discovery={
            "search_url": "https://registry.npmjs.org/-/v1/search",
            "registry_base": "https://registry.npmjs.org",
            "search_queries": ["mcp-server-"],
            "name_prefixes": ["mcp-server-"],
            "max_items_per_cycle": 100,
        },
    )


def _npm_packument(name: str) -> dict[str, Any]:
    return {
        "name": name,
        "description": "An MCP package",
        "dist-tags": {"latest": "1.0.0"},
        "versions": {
            "1.0.0": {
                "name": name,
                "description": "An MCP package",
                "repository": {"type": "git", "url": f"git+https://github.com/acme/{name}.git"},
                "license": "MIT",
            }
        },
    }


class _FakeNpmClient:
    """Routes `.get(url)` between the search API and packument fetches.

    A `/-/v1/search` request returns one page of `objects` built from `search_names`
    (fewer than the page size, so the adapter's pagination stops after one page). A
    packument request returns the doc for the matching name (200 by default, or the
    status in `statuses[name]`); `interrupt_on` raises CancelledError when that
    package's packument is fetched (a worker cancel mid-walk).
    """

    def __init__(
        self,
        *,
        search_names: list[str],
        statuses: dict[str, int] | None = None,
        interrupt_on: str | None = None,
    ) -> None:
        self._search_names = search_names
        self._statuses = statuses or {}
        self._interrupt_on = interrupt_on
        self.calls: list[str] = []

    async def get(self, url: str, **_: Any) -> Any:
        self.calls.append(url)
        if "/-/v1/search" in url:
            return _make_response(
                {
                    "objects": [{"package": {"name": n}} for n in self._search_names],
                    "total": len(self._search_names),
                }
            )
        # Packument fetch — match the (possibly %2F-encoded) name at the URL tail.
        for name in self._search_names:
            if url.endswith(name.replace("/", "%2F")):
                if self._interrupt_on == name:
                    raise asyncio.CancelledError
                status = self._statuses.get(name, 200)
                if status == 304:
                    resp = MagicMock()
                    resp.status_code = 304
                    resp.headers = {"etag": '"x"'}
                    resp.content = b""
                    return resp
                return _make_response(_npm_packument(name), status=status)
        return _make_response({}, status=404)


def _npm_patches(write_cursor: AsyncMock) -> Any:
    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)
    mock_session.commit = AsyncMock()
    return (
        patch("app.db.session.AsyncSessionLocal", return_value=mock_session),
        patch("app.ingestion.framework.cursor.read_cursor", AsyncMock(return_value={})),
        patch("app.ingestion.framework.cursor.write_cursor", write_cursor),
    )


@pytest.mark.asyncio
async def test_npm_search_yields_prefix_matches_and_resets_cursor() -> None:
    """The search API enumerates candidates; only names that actually start with a
    configured prefix are fetched (search is fuzzy), and a fully-walked cycle writes
    the terminal cursor with success=True (resets the streak)."""
    from app.ingestion.sources.npm import NpmAdapter

    adapter = NpmAdapter(_npm_config())
    # Two fuzzy hits — one true prefix match, one unrelated (must be dropped).
    client = _FakeNpmClient(search_names=["mcp-server-foo", "totally-unrelated-lib"])

    write_cursor = AsyncMock()
    p1, p2, p3 = _npm_patches(write_cursor)
    with p1, p2, p3:
        items = [item async for item in adapter.list_items(client)]

    # Only the prefix match is fetched + yielded.
    assert len(items) == 1
    assert items[0].source_id == "npm/mcp-server-foo"
    assert items[0].http_status == 200
    # The non-matching name never triggered a packument GET.
    assert not any("totally-unrelated-lib" in c for c in client.calls)
    write_cursor.assert_awaited_once()
    await_args: Any = write_cursor.await_args
    assert await_args.kwargs.get("success") is True


@pytest.mark.asyncio
async def test_npm_packument_non_200_isolated_cycle_still_succeeds() -> None:
    """A single packument non-200 yields an error RawItem but does NOT fail the cycle —
    the walk still completes and writes success=True (per-item isolation, like pypi)."""
    from app.ingestion.sources.npm import NpmAdapter

    adapter = NpmAdapter(_npm_config())
    client = _FakeNpmClient(
        search_names=["mcp-server-ok", "mcp-server-bad"],
        statuses={"mcp-server-bad": 503},
    )

    write_cursor = AsyncMock()
    p1, p2, p3 = _npm_patches(write_cursor)
    with p1, p2, p3:
        items = [item async for item in adapter.list_items(client)]

    assert {it.http_status for it in items} == {200, 503}
    write_cursor.assert_awaited_once()
    await_args: Any = write_cursor.await_args
    assert await_args.kwargs.get("success") is True  # one bad packument ≠ a failed cycle


@pytest.mark.asyncio
async def test_npm_cursor_failure_on_interrupt() -> None:
    """A worker-cancel mid-walk still writes a TERMINAL cursor (success=False) via the
    `finally`, advancing the streak rather than silently skipping the write."""
    from app.ingestion.sources.npm import NpmAdapter

    adapter = NpmAdapter(_npm_config())
    client = _FakeNpmClient(
        search_names=["mcp-server-foo", "mcp-server-bar"],
        interrupt_on="mcp-server-bar",
    )

    write_cursor = AsyncMock()
    p1, p2, p3 = _npm_patches(write_cursor)
    with p1, p2, p3, pytest.raises(asyncio.CancelledError):
        _ = [item async for item in adapter.list_items(client)]

    write_cursor.assert_awaited_once()
    await_args: Any = write_cursor.await_args
    assert await_args.kwargs.get("success") is False
