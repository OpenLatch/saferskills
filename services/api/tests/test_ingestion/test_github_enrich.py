"""Tests for the shared GitHub enrich helper (framework/github_enrich.py)."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.ingestion.framework.base_adapter import NormalizedItem
from app.ingestion.framework.github_enrich import enrich_repo_facts, parse_github_coords


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://github.com/acme/widget", ("acme", "widget")),
        ("https://github.com/acme/widget.git", ("acme", "widget")),
        ("https://github.com/acme/widget#readme", ("acme", "widget")),
        ("https://github.com/acme/widget?tab=readme", ("acme", "widget")),
        ("https://github.com/acme/widget/tree/main/sub", ("acme", "widget")),
        ("git+https://github.com/acme/widget.git", ("acme", "widget")),
        ("https://gitlab.com/acme/widget", (None, None)),
        ("https://example.com/foo", (None, None)),
        ("", (None, None)),
        (None, (None, None)),
    ],
)
def test_parse_github_coords(url: str | None, expected: tuple[str | None, str | None]) -> None:
    assert parse_github_coords(url) == expected


def _normalized(**kw: Any) -> NormalizedItem:
    return NormalizedItem(
        github_org=kw.get("github_org", "acme"),
        github_repo=kw.get("github_repo", "widget"),
        display_name="widget",
    )


def _resp(
    data: dict[str, Any] | None = None, *, status: int = 200, content: bytes = b""
) -> MagicMock:
    r = MagicMock()
    r.status_code = status
    r.json = lambda: data or {}
    r.content = content
    return r


@pytest.mark.asyncio
async def test_enrich_noop_without_coords() -> None:
    client = AsyncMock()
    n = _normalized(github_org=None, github_repo=None)
    await enrich_repo_facts(client, n)
    client.get.assert_not_called()
    assert n.stars is None


@pytest.mark.asyncio
async def test_enrich_populates_repo_facts_and_manifests() -> None:
    repo_facts = {
        "stargazers_count": 42,
        "size": 1234,
        "default_branch": "trunk",
        "pushed_at": "2026-01-01T00:00:00Z",
        "archived": False,
        "license": {"spdx_id": "Apache-2.0"},
    }

    async def fake_get(url: str, *a: Any, **k: Any) -> MagicMock:
        if url.startswith("https://api.github.com/repos/"):
            return _resp(repo_facts)
        if url.endswith("/SKILL.md"):
            return _resp(content=b"# Skill")
        return _resp(status=404)

    client = MagicMock()
    client.get = AsyncMock(side_effect=fake_get)

    n = _normalized()
    await enrich_repo_facts(client, n, manifest_files=("SKILL.md", "README.md"))

    assert n.stars == 42
    assert n.payload_hint.get("commit_count") == 1234
    assert n.default_branch == "trunk"
    assert n.pushed_at == "2026-01-01T00:00:00Z"
    assert n.license_spdx == "Apache-2.0"
    assert n.metadata_files["SKILL.md"] == b"# Skill"
    assert "README.md" not in n.metadata_files  # 404 → not stored


@pytest.mark.asyncio
async def test_enrich_ignores_noassertion_license() -> None:
    client = MagicMock()
    client.get = AsyncMock(
        return_value=_resp({"stargazers_count": 1, "license": {"spdx_id": "NOASSERTION"}})
    )
    n = _normalized()
    await enrich_repo_facts(client, n, manifest_files=())
    assert n.license_spdx is None


@pytest.mark.asyncio
async def test_enrich_swallows_fetch_errors() -> None:
    client = MagicMock()
    client.get = AsyncMock(side_effect=RuntimeError("network down"))
    n = _normalized()
    await enrich_repo_facts(client, n)  # must not raise
    assert n.stars is None
