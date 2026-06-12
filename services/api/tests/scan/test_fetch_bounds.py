"""Regression tests for the per-repo in-memory file-index bounds (memory redesign).

Pins the OOM root-cause fix: the tarball/walk path used to load the ENTIRE
uncompressed repo into RAM (`MAX_TARBALL_BYTES` caps only the compressed
stream), while the Git Trees path was bounded — asymmetric caps AND a
fileset-parity bug (the same repo could score different filesets depending on
which path fetched it). Both paths now share `IndexBudget` /
`select_index_within_bounds`, applied in sorted-path order.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from urllib.parse import unquote

import httpx
import pytest

from app.scan import fetch
from app.scan.engine import run_repo_scan
from app.scan.fetch import (
    MAX_PER_FILE_BYTES,
    collect_bounded_index,
    select_index_within_bounds,
)

REF_SHA = "a" * 40
URL = "https://github.com/acme/textheavy"


# ── pure policy unit tests ──────────────────────────────────────────────────


def test_select_index_within_bounds_is_sticky() -> None:
    """Once a bound trips, NO later file is admitted (no best-fit backfill)."""
    kept, skipped = select_index_within_bounds(
        [("a.md", 3), ("b.md", 5), ("c.md", 1)],  # b blows the budget; c would fit
        max_files=10,
        max_total_bytes=4,
    )
    assert kept == ["a.md"]
    assert skipped == ["b.md", "c.md"]


def test_select_index_within_bounds_max_files() -> None:
    kept, skipped = select_index_within_bounds(
        [("a.md", 1), ("b.md", 1), ("c.md", 1)],
        max_files=2,
        max_total_bytes=1000,
    )
    assert kept == ["a.md", "b.md"]
    assert skipped == ["c.md"]


def test_walk_files_yields_sorted_paths(tmp_path: Path) -> None:
    """The walk enumerates in sorted posix-path order (fetch-path parity)."""
    (tmp_path / "z.md").write_bytes(b"z")
    (tmp_path / "a.md").write_bytes(b"a")
    sub = tmp_path / "dir"
    sub.mkdir()
    (sub / "m.md").write_bytes(b"m")

    paths = [p for p, _ in fetch.walk_files(tmp_path)]

    assert paths == sorted(paths)
    assert paths == ["a.md", "dir/m.md", "z.md"]


# ── walk-path bounding (the unbounded-index OOM fix) ───────────────────────


def _shrink_bounds(monkeypatch: pytest.MonkeyPatch, *, files: int = 4000, total: int) -> None:
    monkeypatch.setattr(fetch.get_settings(), "scan_max_index_files", files)
    monkeypatch.setattr(fetch.get_settings(), "scan_max_index_total_bytes", total)


def test_collect_bounded_index_caps_total_bytes(monkeypatch: pytest.MonkeyPatch) -> None:
    """The walked stream is admitted only up to the per-repo byte budget."""
    _shrink_bounds(monkeypatch, total=4)
    walked = [("a.md", b"aaa"), ("b.md", b"bbb"), ("c.md", b"c")]

    file_index, skipped = collect_bounded_index(iter(walked))

    assert [p for p, _ in file_index] == ["a.md"]
    assert skipped == ["b.md", "c.md"]


def test_collect_bounded_index_skips_oversized_file_without_charging_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A > 5 MiB file is per-file-skipped (belt) and does NOT trip the budget."""
    _shrink_bounds(monkeypatch, total=100)
    huge = b"x" * (MAX_PER_FILE_BYTES + 1)
    walked = [("big.bin", huge), ("ok.md", b"fine")]

    file_index, skipped = collect_bounded_index(iter(walked))

    assert [p for p, _ in file_index] == ["ok.md"]
    assert skipped == ["big.bin"]


@pytest.mark.asyncio
async def test_walk_path_index_is_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    """run_repo_scan's in-memory index respects the budget; overflow paths land
    in skipped_files (the report contract). FAILS on main (walk path unbounded)."""
    _shrink_bounds(monkeypatch, total=8)
    file_index = [("a.md", b"aaaa"), ("b.md", b"bbbb"), ("c.md", b"cccc")]  # 12 > 8

    async def fake_fetch(_url: str) -> fetch.FetchResult:
        return fetch.FetchResult(
            directory=Path("/tmp/nonexistent"),
            ref_sha=REF_SHA,
            file_count=len(file_index),
            skipped_oversized_files=[],
        )

    def fake_walk(_dir: Path) -> Iterator[tuple[str, bytes]]:
        return iter(file_index)  # already sorted — sorting is walk_files' job

    monkeypatch.setattr(fetch, "fetch_repository", fake_fetch)
    monkeypatch.setattr(fetch, "walk_files", fake_walk)

    repo = await run_repo_scan(URL, rubric_version="testver")

    kept_paths = {p for cap in repo.capabilities for p, _ in cap.result.files_index}
    assert "c.md" not in kept_paths
    assert "c.md" in repo.skipped_files


# ── fetch-path parity (same fileset whichever path fetched the repo) ────────


def _patch_trees_transport(
    monkeypatch: pytest.MonkeyPatch,
    *,
    tree_entries: list[dict[str, object]],
    blobs: dict[str, bytes],
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if "/git/trees/" in str(request.url):
            return httpx.Response(
                200, json={"sha": REF_SHA, "truncated": False, "tree": tree_entries}
            )
        parts = request.url.path.split("/")[1:]
        rel = unquote("/".join(parts[3:]))
        return httpx.Response(200, content=blobs[rel])

    real_client = httpx.AsyncClient

    def factory(*_a: object, **kwargs: object) -> httpx.AsyncClient:
        kwargs.pop("transport", None)
        return real_client(transport=httpx.MockTransport(handler), **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(fetch.httpx, "AsyncClient", factory)


@pytest.mark.asyncio
async def test_fetch_path_fileset_parity(monkeypatch: pytest.MonkeyPatch) -> None:
    """With the bounds hit, walk and trees keep the IDENTICAL fileset + skip list.
    FAILS on main (trees capped in tree order, walk not capped at all)."""
    _shrink_bounds(monkeypatch, total=8)
    blobs = {"a.md": b"aaaa", "b.md": b"bbbb", "c.md": b"cccc"}  # sorted: a, b kept; c over

    # Trees path — entries deliberately in NON-sorted order.
    _patch_trees_transport(
        monkeypatch,
        tree_entries=[
            {"path": "c.md", "type": "blob", "size": 4, "sha": "f" * 40},
            {"path": "a.md", "type": "blob", "size": 4, "sha": "f" * 40},
            {"path": "b.md", "type": "blob", "size": 4, "sha": "f" * 40},
        ],
        blobs=blobs,
    )
    trees_index, trees_skipped = await fetch.fetch_file_index_via_trees(
        URL, ref_sha=REF_SHA, default_branch="main"
    )

    # Walk path — same files, sorted enumeration (walk_files contract).
    walk_index, walk_skipped = collect_bounded_index(iter(sorted(blobs.items())))

    assert [p for p, _ in trees_index] == [p for p, _ in walk_index] == ["a.md", "b.md"]
    assert dict(trees_index) == dict(walk_index)
    assert sorted(trees_skipped) == sorted(walk_skipped) == ["c.md"]


@pytest.mark.asyncio
async def test_caps_applied_in_sorted_path_order(monkeypatch: pytest.MonkeyPatch) -> None:
    """max_files=1 over {z.md, a.md} keeps a.md on BOTH paths — deterministic
    sorted-path order, not arrival order. FAILS on main (trees kept tree-order
    winner z.md)."""
    _shrink_bounds(monkeypatch, files=1, total=1000)
    blobs = {"z.md": b"zz", "a.md": b"aa"}

    _patch_trees_transport(
        monkeypatch,
        tree_entries=[
            {"path": "z.md", "type": "blob", "size": 2, "sha": "f" * 40},
            {"path": "a.md", "type": "blob", "size": 2, "sha": "f" * 40},
        ],
        blobs=blobs,
    )
    trees_index, trees_skipped = await fetch.fetch_file_index_via_trees(
        URL, ref_sha=REF_SHA, default_branch="main"
    )

    walk_index, walk_skipped = collect_bounded_index(iter(sorted(blobs.items())))

    assert [p for p, _ in trees_index] == [p for p, _ in walk_index] == ["a.md"]
    assert trees_skipped == walk_skipped == ["z.md"]
