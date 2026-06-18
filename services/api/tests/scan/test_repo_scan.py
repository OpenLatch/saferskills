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
    EngineFinding,
    RepoScanResult,
    ScanResult,
    aggregate_score,
    run_repo_scan,
    run_repo_scan_from_index,
    run_repo_scan_via_trees,
    tier_for,
)


def _finding(
    severity: str, *, status: str = "active", sub_score: str = "security"
) -> EngineFinding:
    """A minimal EngineFinding for scoring tests (penalty from the severity map)."""
    return EngineFinding(
        rule_id=f"SS-SKILL-TEST-{severity.upper()}-01",
        severity=severity,
        sub_score=sub_score,
        penalty=engine.SEVERITY_PENALTY[severity],
        status_at_scan=status,
        file_path="SKILL.md",
        line_start=1,
        line_end=None,
        matched_content_sha256="0" * 64,
        remediation_link="",
        rubric_version="testver",
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


# ── severity ceiling (supersedes the per-sub-score floor) ──────────────────


def test_active_critical_caps_aggregate_at_15_red() -> None:
    """One active critical finding caps the whole aggregate at ≤15 → red, even
    though security is only 35% of the weight (would otherwise sit ~72)."""
    _sub, breakdown, aggregate, tier = aggregate_score([_finding("critical")])
    assert aggregate <= 15
    assert tier == "red"
    ceiling = breakdown["aggregate_math"]["severity_ceiling"]
    assert ceiling["ceiling"] == 15
    assert ceiling["applied"] is True
    assert ceiling["weighted_aggregate"] > 15  # dilution proof: pre-ceiling was high


def test_active_high_caps_aggregate_at_45() -> None:
    """One active high finding (no critical) caps the aggregate at ≤45."""
    _sub, breakdown, aggregate, _tier = aggregate_score([_finding("high")])
    assert aggregate <= 45
    assert breakdown["aggregate_math"]["severity_ceiling"]["ceiling"] == 45
    assert breakdown["aggregate_math"]["severity_ceiling"]["applied"] is True


def test_medium_only_no_ceiling() -> None:
    """medium/low/info never imply a ceiling — score stays the weighted value."""
    sub, breakdown, aggregate, _tier = aggregate_score([_finding("medium")])
    assert breakdown["aggregate_math"]["severity_ceiling"]["ceiling"] is None
    assert breakdown["aggregate_math"]["severity_ceiling"]["applied"] is False
    # security: 100-12=88, others 100 → 0.35*88 + 0.65*100 = 95.8 → 96.
    assert aggregate == round(0.35 * sub["security"] + 0.65 * 100)
    assert aggregate > 45


def test_info_only_no_ceiling_perfect_score() -> None:
    sub, breakdown, aggregate, tier = aggregate_score([_finding("info")])
    assert breakdown["aggregate_math"]["severity_ceiling"]["ceiling"] is None
    assert aggregate == 100  # info carries penalty 0
    assert tier == "green"
    assert sub["security"] == 100


def test_shadow_critical_does_not_trigger_ceiling() -> None:
    """A shadow critical fires + records but must NOT cap the aggregate — only
    ACTIVE high/critical findings do."""
    _sub, breakdown, aggregate, _tier = aggregate_score([_finding("critical", status="shadow")])
    assert breakdown["aggregate_math"]["severity_ceiling"]["ceiling"] is None
    assert aggregate > 15  # not capped


def test_lowest_ceiling_wins_critical_over_high() -> None:
    """With both an active high and an active critical, the lower (critical=15)
    ceiling applies."""
    _sub, _breakdown, aggregate, _tier = aggregate_score(
        [_finding("high"), _finding("critical", sub_score="supply_chain")]
    )
    assert aggregate <= 15


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


def test_repo_rollup_ceiling_caps_one_bad_capability_among_clean(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A repo with one critical capability among many clean ones is capped at 15
    — the rounded-mean rollup (~72 here) must not dilute the failure back up."""
    from app.scan import discovery

    caps = [
        Capability(kind=KIND_SKILL, name=n, component_path=n, file_subset=[(f"{n}/SKILL.md", b"x")])
        for n in ("bad", "clean1", "clean2")
    ]

    def fake_discover(
        _index: list[tuple[str, bytes]], *, source_kind: str | None = None
    ) -> list[Capability]:
        return caps

    def fake_score(cap: Capability, rubric_version: str, ref_sha: str) -> engine.CapabilityResult:
        findings = [_finding("critical")] if cap.name == "bad" else []
        aggregate = 15 if cap.name == "bad" else 100
        result = ScanResult(
            findings=findings,
            sub_scores={},
            score_breakdown={},
            aggregate_score=aggregate,
            tier=tier_for(aggregate),
            file_count=1,
            skipped_rules=[],
            skipped_files=[],
            ref_sha=ref_sha,
            latency_ms=0,
            files_index=list(cap.file_subset),
        )
        return engine.CapabilityResult(
            kind=cap.kind, name=cap.name, component_path=cap.component_path, result=result
        )

    monkeypatch.setattr(discovery, "discover_capabilities", fake_discover)
    monkeypatch.setattr(engine, "score_capability", fake_score)

    repo = run_repo_scan_from_index([("bad/SKILL.md", b"x")], "testver")

    # Plain mean would be round((15+100+100)/3) = 72 (yellow); the ceiling drags
    # the whole repo down to ≤15 (red) because one capability has an active critical.
    assert repo.repo_aggregate_score <= 15
    assert repo.repo_tier == "red"


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
