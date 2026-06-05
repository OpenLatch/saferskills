"""Unit tests for the large-repo Git Trees + raw fetch path.

The Trees `GET` and the per-blob raw `GET`s are mocked via `httpx.MockTransport`
(injected by patching `fetch.httpx.AsyncClient`) — no network is touched. Mirrors
the monkeypatch style of `test_repo_scan.py`.
"""

from __future__ import annotations

from urllib.parse import unquote

import httpx
import pytest

from app.scan import fetch
from app.scan.fetch import MAX_PER_FILE_BYTES, FetchError, fetch_file_index_via_trees

REF_SHA = "a" * 40
URL = "https://github.com/acme/monorepo"


def _raw_relpath(request: httpx.Request) -> str:
    """`raw.githubusercontent.com/<org>/<repo>/<sha>/<path>` → repo-relative path."""
    # path is `/acme/monorepo/<sha>/tools/x.json` → drop org/repo/sha (3 segments).
    parts = request.url.path.split("/")[1:]  # strip leading ''
    return unquote("/".join(parts[3:]))


def _patch_transport(
    monkeypatch: pytest.MonkeyPatch,
    *,
    tree: dict[str, object],
    blobs: dict[str, bytes],
    requested: list[str] | None = None,
    tree_status: int = 200,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "/git/trees/" in url:
            return httpx.Response(tree_status, json=tree)
        rel = _raw_relpath(request)
        if requested is not None:
            requested.append(rel)
        return httpx.Response(200, content=blobs[rel])

    real_client = httpx.AsyncClient

    def factory(*_a: object, **kwargs: object) -> httpx.AsyncClient:
        kwargs.pop("transport", None)
        return real_client(transport=httpx.MockTransport(handler), **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(fetch.httpx, "AsyncClient", factory)


def _tree(*entries: dict[str, object], truncated: bool = False) -> dict[str, object]:
    return {"sha": REF_SHA, "truncated": truncated, "tree": list(entries)}


def _blob(path: str, size: int) -> dict[str, object]:
    return {"path": path, "type": "blob", "size": size, "sha": "f" * 40}


@pytest.mark.asyncio
async def test_builds_file_index(monkeypatch: pytest.MonkeyPatch) -> None:
    blobs = {"tools/x.json": b'{"a": 1}', "README.md": b"# hi"}
    tree = _tree(
        _blob("tools/x.json", len(blobs["tools/x.json"])),
        {"path": "tools", "type": "tree"},  # non-blob entry ignored
        _blob("README.md", len(blobs["README.md"])),
    )
    _patch_transport(monkeypatch, tree=tree, blobs=blobs)

    file_index, skipped = await fetch_file_index_via_trees(
        URL, ref_sha=REF_SHA, default_branch="main"
    )

    assert skipped == []
    assert dict(file_index) == blobs
    assert len(file_index) == 2


@pytest.mark.asyncio
async def test_oversized_blob_skipped_not_fetched(monkeypatch: pytest.MonkeyPatch) -> None:
    """A blob > 5 MiB goes to skipped_oversized (parity with the tarball skip) and
    is never fetched from raw."""
    blobs = {"small.md": b"ok"}
    tree = _tree(
        _blob("small.md", len(blobs["small.md"])),
        _blob("huge.bin", MAX_PER_FILE_BYTES + 1),
    )
    requested: list[str] = []
    _patch_transport(monkeypatch, tree=tree, blobs=blobs, requested=requested)

    file_index, skipped = await fetch_file_index_via_trees(
        URL, ref_sha=REF_SHA, default_branch="main"
    )

    assert dict(file_index) == blobs
    assert skipped == ["huge.bin"]
    assert "huge.bin" not in requested  # never fetched


@pytest.mark.asyncio
async def test_truncated_tree_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    tree = _tree(_blob("a.md", 2), truncated=True)
    _patch_transport(monkeypatch, tree=tree, blobs={"a.md": b"hi"})

    with pytest.raises(FetchError, match="truncated"):
        await fetch_file_index_via_trees(URL, ref_sha=REF_SHA, default_branch="main")


@pytest.mark.asyncio
async def test_tree_404_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_transport(monkeypatch, tree={}, blobs={}, tree_status=404)

    with pytest.raises(FetchError, match="tree not found"):
        await fetch_file_index_via_trees(URL, ref_sha=REF_SHA, default_branch="main")


@pytest.mark.asyncio
async def test_max_files_bound_enforced(monkeypatch: pytest.MonkeyPatch) -> None:
    """scan_trees_max_files caps the kept set; the rest are skipped gracefully."""
    monkeypatch.setattr(fetch.get_settings(), "scan_trees_max_files", 1)
    blobs = {"a.md": b"a", "b.md": b"b"}
    tree = _tree(_blob("a.md", 1), _blob("b.md", 1))
    _patch_transport(monkeypatch, tree=tree, blobs=blobs)

    file_index, skipped = await fetch_file_index_via_trees(
        URL, ref_sha=REF_SHA, default_branch="main"
    )

    assert len(file_index) == 1
    assert [p for p, _ in file_index] == ["a.md"]
    assert skipped == ["b.md"]


@pytest.mark.asyncio
async def test_max_total_bytes_bound_enforced(monkeypatch: pytest.MonkeyPatch) -> None:
    """scan_trees_max_total_bytes stops fetching once the per-repo budget is hit."""
    monkeypatch.setattr(fetch.get_settings(), "scan_trees_max_total_bytes", 4)
    blobs = {"a.md": b"aaa", "b.md": b"bbb"}  # 3 + 3 = 6 > 4
    tree = _tree(_blob("a.md", 3), _blob("b.md", 3))
    _patch_transport(monkeypatch, tree=tree, blobs=blobs)

    file_index, skipped = await fetch_file_index_via_trees(
        URL, ref_sha=REF_SHA, default_branch="main"
    )

    assert [p for p, _ in file_index] == ["a.md"]
    assert skipped == ["b.md"]


@pytest.mark.asyncio
async def test_raw_urls_pinned_to_ref_sha(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every raw fetch must be pinned to the resolved SHA (reproducible)."""
    captured: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "/git/trees/" in url:
            return httpx.Response(200, json=_tree(_blob("dir/f.txt", 2)))
        captured.append(url)
        return httpx.Response(200, content=b"hi")

    real_client = httpx.AsyncClient

    def factory(*_a: object, **kwargs: object) -> httpx.AsyncClient:
        kwargs.pop("transport", None)
        return real_client(transport=httpx.MockTransport(handler), **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(fetch.httpx, "AsyncClient", factory)

    await fetch_file_index_via_trees(URL, ref_sha=REF_SHA, default_branch="main")

    assert captured == [f"https://raw.githubusercontent.com/acme/monorepo/{REF_SHA}/dir/f.txt"]
