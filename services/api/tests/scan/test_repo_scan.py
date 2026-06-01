"""Unit tests for per-capability scoring + repo rollup (engine.run_repo_scan).

Pure-logic: the GitHub fetch is monkeypatched, so no network is touched.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.scan import engine, fetch
from app.scan.discovery import KIND_SKILL, Capability
from app.scan.engine import aggregate_score, run_repo_scan, tier_for


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
    scored = engine._score_capability(cap, rubric_version="testver", ref_sha="a" * 40)
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

    monkeypatch.setattr(fetch, "fetch_repository", fake_fetch)
    monkeypatch.setattr(fetch, "walk_files", lambda _dir: iter(file_index))

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
