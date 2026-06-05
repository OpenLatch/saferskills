"""Unit tests for per-capability scoring + repo rollup (engine.run_repo_scan).

Pure-logic: the GitHub fetch is monkeypatched, so no network is touched.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterator
from pathlib import Path

import pytest

from app.scan import engine, fetch, persistence
from app.scan.discovery import KIND_SKILL, Capability
from app.scan.engine import (
    RepoScanResult,
    aggregate_score,
    run_repo_scan,
    run_repo_scan_via_trees,
    tier_for,
)


def test_tier_bands() -> None:
    assert tier_for(100) == "green"
    assert tier_for(80) == "green"
    assert tier_for(79) == "yellow"
    assert tier_for(60) == "yellow"
    assert tier_for(40) == "orange"
    assert tier_for(39) == "red"
    assert tier_for(0) == "red"


def test_empty_findings_aggregate_is_perfect_green() -> None:
    sub_scores, _breakdown, aggregate, tier = aggregate_score([])
    assert aggregate == 100
    assert tier == "green"
    assert all(v == 100 for v in sub_scores.values())


def test_score_capability_clean_skill_scores_100() -> None:
    cap = Capability(
        kind=KIND_SKILL,
        name="clean",
        component_path="",
        file_subset=[("SKILL.md", b"# fine")],
    )
    scored = engine.score_capability(cap, rubric_version="testver", ref_sha="a" * 40)
    assert scored.kind == KIND_SKILL
    assert scored.name == "clean"
    assert scored.result.file_count == 1
    assert scored.result.ref_sha == "a" * 40
    # A no-finding capability aggregates to 100/green.
    assert scored.result.aggregate_score == 100
    assert scored.result.tier == "green"


@pytest.mark.asyncio
async def test_run_repo_scan_rollup_is_mean_and_tally(monkeypatch: pytest.MonkeyPatch) -> None:
    file_index = [
        ("skills/a/SKILL.md", b"---\nname: a\n---\n"),
        ("skills/b/SKILL.md", b"---\nname: b\n---\n"),
        ("hooks/h.json", b'{"command": "x"}'),
        ("LICENSE", b"MIT"),
    ]

    async def fake_fetch(_url: str) -> fetch.FetchResult:
        return fetch.FetchResult(
            directory=Path("/tmp/nonexistent"),
            ref_sha="b" * 40,
            file_count=len(file_index),
            skipped_oversized_files=[],
        )

    def fake_walk(_dir: Path) -> Iterator[tuple[str, bytes]]:
        return iter(file_index)

    monkeypatch.setattr(fetch, "fetch_repository", fake_fetch)
    monkeypatch.setattr(fetch, "walk_files", fake_walk)

    repo = await run_repo_scan("https://github.com/acme/kit", rubric_version="testver")

    assert repo.capability_count == 3
    assert repo.kind_tally == {"skill": 2, "hook": 1}
    assert repo.ref_sha == "b" * 40

    # Repo aggregate is the rounded mean of per-capability scores.
    scores = [c.result.aggregate_score for c in repo.capabilities]
    assert repo.repo_aggregate_score == round(sum(scores) / len(scores))
    assert repo.repo_tier == tier_for(repo.repo_aggregate_score)
    # Every capability carries the shared repo ref + an independent score.
    assert all(c.result.ref_sha == "b" * 40 for c in repo.capabilities)


def _snapshot_identity(repo: RepoScanResult) -> str:
    """The stable content hash of the scanned tree, the way persistence computes it."""
    file_map: dict[str, str | None] = {}
    for cap in repo.capabilities:
        for path, content in cap.result.files_index:
            file_map[path] = hashlib.sha256(content).hexdigest()
    return persistence._snapshot_identity(file_map)  # pyright: ignore[reportPrivateUsage]


@pytest.mark.asyncio
async def test_tarball_and_trees_paths_are_equivalent(monkeypatch: pytest.MonkeyPatch) -> None:
    """Equivalence guarantee: the tarball path and the Git Trees path, fed the
    identical fileset, produce a byte-identical RepoScanResult + snapshot identity.
    Only how the bytes arrive differs."""
    file_index = [
        ("skills/a/SKILL.md", b"---\nname: a\n---\n"),
        ("skills/b/SKILL.md", b"---\nname: b\n---\n"),
        ("hooks/h.json", b'{"command": "x"}'),
        ("LICENSE", b"MIT"),
    ]
    ref_sha = "c" * 40

    # ── tarball path ──
    async def fake_fetch(_url: str) -> fetch.FetchResult:
        return fetch.FetchResult(
            directory=Path("/tmp/nonexistent"),
            ref_sha=ref_sha,
            file_count=len(file_index),
            skipped_oversized_files=[],
        )

    def fake_walk(_dir: Path) -> Iterator[tuple[str, bytes]]:
        return iter(file_index)

    monkeypatch.setattr(fetch, "fetch_repository", fake_fetch)
    monkeypatch.setattr(fetch, "walk_files", fake_walk)
    via_tarball = await run_repo_scan("https://github.com/acme/kit", rubric_version="testver")

    # ── trees path (same fileset) ──
    async def fake_trees(
        _url: str, *, ref_sha: str, default_branch: str
    ) -> tuple[list[tuple[str, bytes]], list[str]]:
        return list(file_index), []

    monkeypatch.setattr(fetch, "fetch_file_index_via_trees", fake_trees)
    via_trees = await run_repo_scan_via_trees(
        "https://github.com/acme/kit", "testver", ref_sha=ref_sha, default_branch="main"
    )

    # Identical scores, tier, tally, capability set.
    assert via_trees.repo_aggregate_score == via_tarball.repo_aggregate_score
    assert via_trees.repo_tier == via_tarball.repo_tier
    assert via_trees.kind_tally == via_tarball.kind_tally
    assert via_trees.capability_count == via_tarball.capability_count
    assert {(c.kind, c.name) for c in via_trees.capabilities} == {
        (c.kind, c.name) for c in via_tarball.capabilities
    }
    # Identical snapshot identity → byte-identical stored snapshot + zip + content hash.
    assert _snapshot_identity(via_trees) == _snapshot_identity(via_tarball)
