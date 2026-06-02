"""Generic detector runtime.

Three trigger types fire in Phase B:

- `regex_match` — compile the rule's pattern (with flags), scan every file
  whose path matches the rule's `trigger.scope.paths` glob list. Each match
  yields one Finding pinned to (file_path, line_start, matched_content_sha256).
- `file_glob_absent` — for each pattern in `trigger.absentPaths`, if NO file
  matches, fire one Finding pinned to that pattern.
- `metadata_check` — for each pattern in `trigger.fileGlob`, parse JSON/YAML,
  evaluate `trigger.predicate` against the resulting dict. Phase B supports the
  `missing_field` and `field_equals` predicates.

`commit_history_check` and `composite_and_or` rules are recognised but the
engine does NOT fire them — they are reported as `skipped_rules` on the
ScanResult so the queue worker can emit a per-stage NOTICE that surfaces in
the SSE progress feed.

Scoring follows the rubric `scan-report.schema.json` contract:

- Each finding contributes `penalty` (clamped 0-40) to its sub-score.
- `raw_sub_score = max(0, 100 - sum(penalties))`.
- If any contributing finding has severity=critical: `final_sub_score = min(raw, 40)`.
- Aggregate = sum of (final_sub_score * weight) where weights are
  35 / 20 / 15 / 15 / 15 per the PRD (security / supply_chain / maintenance /
  transparency / community).
- Tier: ≥80 green, ≥60 yellow, ≥40 orange, <40 red.
"""

from __future__ import annotations

import fnmatch
import hashlib
import json
import re
import time
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import yaml

from app.scan import fetch
from app.scan.rubric import RULES, RubricRule, SubScore

if TYPE_CHECKING:
    from app.scan.discovery import Capability

# Severity → penalty mapping per D-02. `info` is advisory (weight 0).
SEVERITY_PENALTY: dict[str, int] = {
    "info": 0,
    "low": 5,
    "medium": 12,
    "high": 25,
    "critical": 40,
}

SUB_SCORE_WEIGHTS: dict[str, int] = {
    "security": 35,
    "supply_chain": 20,
    "maintenance": 15,
    "transparency": 15,
    "community": 15,
}

SUB_SCORES: tuple[str, ...] = (
    "security",
    "supply_chain",
    "maintenance",
    "transparency",
    "community",
)


@dataclass
class EngineFinding:
    """Pre-DB finding — the queue worker converts this into a `findings` row."""

    rule_id: str
    severity: str
    sub_score: str
    penalty: int
    status_at_scan: str
    file_path: str
    line_start: int
    line_end: int | None
    matched_content_sha256: str
    remediation_link: str
    rubric_version: str


@dataclass
class SubScoreBreakdown:
    finding_ids: list[str]
    raw_sub_score: int
    critical_floor_applied: bool
    final_sub_score: int
    weighted_contribution: float


@dataclass
class ScanResult:
    findings: list[EngineFinding]
    sub_scores: dict[str, int]
    score_breakdown: dict[str, Any]
    aggregate_score: int
    tier: str
    file_count: int
    skipped_rules: list[str]
    skipped_files: list[str]
    ref_sha: str
    latency_ms: int
    files_index: list[tuple[str, bytes]] = field(default_factory=list)  # type: ignore[arg-type]


@dataclass
class CapabilityResult:
    """One discovered capability + its independent scan result."""

    kind: str
    name: str
    component_path: str
    result: ScanResult


@dataclass
class RepoScanResult:
    """Rollup of a repo scan over its N discovered capabilities.

    `repo_aggregate_score` is the mean of the per-capability aggregate scores
    (the consolidated capabilities score the report surfaces); `kind_tally`
    counts capabilities by kind for the report's by-kind tally.
    """

    capabilities: list[CapabilityResult]
    repo_aggregate_score: int
    repo_tier: str
    kind_tally: dict[str, int]
    capability_count: int
    ref_sha: str
    file_count: int
    latency_ms: int
    skipped_files: list[str]


# ── trigger evaluators ────────────────────────────────────────────────────


def _match_any_glob(path: str, patterns: Iterable[str]) -> bool:
    posix = path.replace("\\", "/")
    return any(_fnmatch_recursive(posix, pat.replace("\\", "/")) for pat in patterns)


# Public alias — the single glob matcher reused by `app.scan.discovery` (no 2nd
# matcher in the scan package). Kept distinct from the underscore-internal name
# so cross-module callers don't trip the private-usage lint.
match_any_glob = _match_any_glob


def _fnmatch_recursive(path: str, pattern: str) -> bool:
    """fnmatch with `**` support — `**/X` matches X at any depth INCLUDING the
    root, so `**/*.md` matches `SKILL.md` as well as `docs/SKILL.md`. Used so
    rubric scope globs work the way the YAML author expected.
    """
    sentinel = "@@DOUBLESTAR@@"
    # `**/foo` should match `foo` at root → strip the leading `**/` and try
    # the bare tail first; if that misses, fall through to the full `**`-
    # anywhere translation.
    if pattern.startswith("**/") and _fnmatch_recursive(path, pattern[3:]):
        return True
    protected = pattern.replace("**", sentinel)
    regex = fnmatch.translate(protected)
    # `.*?` (non-greedy any chars including `/`) is the closest equivalent
    # to the bash `**` glob — accepts zero or more path segments.
    regex = regex.replace(re.escape(sentinel), ".*?")
    return re.match(regex, path) is not None


def _evaluate_regex_match(
    rule: RubricRule, file_index: list[tuple[str, bytes]], rubric_version: str
) -> list[EngineFinding]:
    trigger = rule.trigger
    pattern_str = trigger.get("pattern")
    if not pattern_str:
        return []
    flags = re.MULTILINE
    if "i" in str(trigger.get("flags", "")).lower():
        flags |= re.IGNORECASE
    if "s" in str(trigger.get("flags", "")).lower():
        flags |= re.DOTALL
    try:
        pattern = re.compile(pattern_str, flags=flags)
    except re.error:
        return []

    scope_paths = trigger.get("scope", {}).get("paths", [])
    in_scope = (
        file_index
        if not scope_paths
        else [(p, b) for p, b in file_index if _match_any_glob(p, scope_paths)]
    )

    penalty = SEVERITY_PENALTY.get(rule.severity, 0)
    findings: list[EngineFinding] = []
    for file_path, content in in_scope:
        text = content.decode("utf-8", errors="replace")
        for match in pattern.finditer(text):
            matched_text = match.group(0)
            line_start = text[: match.start()].count("\n") + 1
            line_end = line_start + matched_text.count("\n") or None
            matched_sha = hashlib.sha256(matched_text.encode("utf-8")).hexdigest()
            findings.append(
                EngineFinding(
                    rule_id=rule.rule_id,
                    severity=rule.severity,
                    sub_score=rule.sub_score,
                    penalty=penalty,
                    status_at_scan=rule.status,
                    file_path=file_path,
                    line_start=line_start,
                    line_end=line_end,
                    matched_content_sha256=matched_sha,
                    remediation_link=rule.remediation_link,
                    rubric_version=rubric_version,
                )
            )
    return findings


def _evaluate_file_glob_absent(
    rule: RubricRule, file_index: list[tuple[str, bytes]], rubric_version: str
) -> list[EngineFinding]:
    absent_paths = rule.trigger.get("absentPaths", [])
    findings: list[EngineFinding] = []
    penalty = SEVERITY_PENALTY.get(rule.severity, 0)
    for pattern in absent_paths:
        if not any(_match_any_glob(p, [pattern]) for p, _ in file_index):
            absence_marker = hashlib.sha256(pattern.encode("utf-8")).hexdigest()
            findings.append(
                EngineFinding(
                    rule_id=rule.rule_id,
                    severity=rule.severity,
                    sub_score=rule.sub_score,
                    penalty=penalty,
                    status_at_scan=rule.status,
                    file_path=pattern,
                    line_start=1,
                    line_end=None,
                    matched_content_sha256=absence_marker,
                    remediation_link=rule.remediation_link,
                    rubric_version=rubric_version,
                )
            )
    return findings


def _evaluate_metadata_check(
    rule: RubricRule, file_index: list[tuple[str, bytes]], rubric_version: str
) -> list[EngineFinding]:
    trigger = rule.trigger
    file_glob = trigger.get("fileGlob")
    predicate = trigger.get("predicate", {})
    if not file_glob or not predicate:
        return []

    penalty = SEVERITY_PENALTY.get(rule.severity, 0)
    findings: list[EngineFinding] = []
    for file_path, content in file_index:
        if not _match_any_glob(file_path, [file_glob]):
            continue
        text = content.decode("utf-8", errors="replace")
        parsed: Any
        if file_path.endswith((".json",)):
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                continue
        elif file_path.endswith((".yaml", ".yml")):
            try:
                parsed = yaml.safe_load(text)
            except yaml.YAMLError:
                continue
        else:
            continue

        if _predicate_holds(predicate, parsed):
            target_field = predicate.get("field", "<root>")
            marker = hashlib.sha256(f"{file_path}:{target_field}".encode()).hexdigest()
            findings.append(
                EngineFinding(
                    rule_id=rule.rule_id,
                    severity=rule.severity,
                    sub_score=rule.sub_score,
                    penalty=penalty,
                    status_at_scan=rule.status,
                    file_path=file_path,
                    line_start=1,
                    line_end=None,
                    matched_content_sha256=marker,
                    remediation_link=rule.remediation_link,
                    rubric_version=rubric_version,
                )
            )
    return findings


def _predicate_holds(predicate: dict[str, Any], parsed: Any) -> bool:
    """Evaluate a metadata-check predicate. Phase B supports two ops:

    - `missing_field`: parsed is dict + the specified field is absent.
    - `field_equals`: parsed[field] == specified value.
    """
    op = predicate.get("op", "missing_field")
    field_path = predicate.get("field", "")
    parts = [p for p in field_path.split(".") if p]
    if not isinstance(parsed, dict):
        return False
    cursor: dict[str, Any] | None = parsed  # type: ignore[assignment]
    for part in parts[:-1]:
        if cursor is None:
            break
        next_value: Any = cursor.get(part)
        cursor = next_value if isinstance(next_value, dict) else None  # type: ignore[assignment]
    target_key = parts[-1] if parts else ""

    if op == "missing_field":
        return cursor is None or target_key not in cursor
    if op == "field_equals":
        expected = predicate.get("value")
        if cursor is None:
            return False
        return cursor.get(target_key) == expected
    return False


# ── orchestration ────────────────────────────────────────────────────────


def _evaluate_rules(
    rules: list[RubricRule],
    file_index: list[tuple[str, bytes]],
    rubric_version: str,
    sub_score_filter: SubScore | None = None,
) -> tuple[list[EngineFinding], list[str]]:
    """Evaluate every rule (optionally filtered by sub-score). Returns
    (findings, skipped_rule_ids).
    """
    findings: list[EngineFinding] = []
    skipped: list[str] = []
    for rule in rules:
        if sub_score_filter is not None and rule.sub_score != sub_score_filter:
            continue
        if not rule.is_directly_evaluable:
            skipped.append(rule.rule_id)
            continue
        if rule.trigger_type == "regex_match":
            findings.extend(_evaluate_regex_match(rule, file_index, rubric_version))
        elif rule.trigger_type == "file_glob_absent":
            findings.extend(_evaluate_file_glob_absent(rule, file_index, rubric_version))
        elif rule.trigger_type == "metadata_check":
            findings.extend(_evaluate_metadata_check(rule, file_index, rubric_version))
    return findings, skipped


def tier_for(score: int) -> str:
    """Map an aggregate score to its tier band. Single source for the bands so
    the per-capability and repo-rollup paths never drift."""
    if score >= 80:
        return "green"
    if score >= 60:
        return "yellow"
    if score >= 40:
        return "orange"
    return "red"


def aggregate_score(
    findings: list[EngineFinding],
) -> tuple[dict[str, int], dict[str, Any], int, str]:
    """Compute sub_scores + score_breakdown + aggregate + tier from findings.

    Returns (sub_scores, score_breakdown, aggregate, tier).
    """
    sub_scores: dict[str, int] = {}
    breakdowns: dict[str, Any] = {}
    weighted_total = 0.0
    formula_parts: list[str] = []
    weights_used: dict[str, float] = {}

    for sub_score in SUB_SCORES:
        contributing = [f for f in findings if f.sub_score == sub_score]
        finding_ids: list[str] = []  # populated later when DB IDs exist
        raw = max(0, 100 - sum(f.penalty for f in contributing))
        critical_floor = any(f.severity == "critical" for f in contributing)
        final = min(raw, 40) if critical_floor else raw
        weight = SUB_SCORE_WEIGHTS[sub_score]
        weighted = final * weight / 100.0

        sub_scores[sub_score] = final
        breakdowns[sub_score] = {
            "finding_ids": finding_ids,
            "raw_sub_score": raw,
            "critical_floor_applied": critical_floor,
            "final_sub_score": final,
            "weighted_contribution": round(weighted, 2),
        }
        weighted_total += weighted
        formula_parts.append(f"{weight}% x {final}")
        weights_used[sub_score] = round(weighted, 2)

    aggregate = round(weighted_total)
    tier = tier_for(aggregate)

    breakdowns["aggregate_math"] = {
        "formula": " + ".join(formula_parts),
        "weighted_contributions": weights_used,
        "tier_mapping": f"aggregate {aggregate} → tier {tier}",
    }

    return sub_scores, breakdowns, aggregate, tier


async def run_scan(
    github_url: str,
    rubric_version: str,
    kind: str | None = None,
) -> ScanResult:
    """Top-level entry point. Fetches the repo, walks files, evaluates rules,
    aggregates a score. Idempotent given (github_url, rubric_version, ref_sha).
    """
    started = time.monotonic()
    result = await fetch.fetch_repository(github_url)
    file_index: list[tuple[str, bytes]] = list(fetch.walk_files(result.directory))

    rules = list(RULES.values())
    if kind is not None:
        from app.scan.rubric import by_kind

        rules = by_kind(kind)

    findings, skipped = _evaluate_rules(rules, file_index, rubric_version)
    sub_scores, breakdown, aggregate, tier = aggregate_score(findings)
    latency_ms = int((time.monotonic() - started) * 1000)

    return ScanResult(
        findings=findings,
        sub_scores=sub_scores,
        score_breakdown=breakdown,
        aggregate_score=aggregate,
        tier=tier,
        file_count=result.file_count,
        skipped_rules=skipped,
        skipped_files=result.skipped_oversized_files,
        ref_sha=result.ref_sha,
        latency_ms=latency_ms,
        files_index=file_index,
    )


def score_capability(
    cap: Capability,
    rubric_version: str,
    ref_sha: str,
) -> CapabilityResult:
    """Score one discovered capability over its kind-scoped rules + subtree.

    Kind-scoped: only rules whose `appliesTo` includes the capability's kind run
    (`rubric.by_kind`) — an embedded hook is only HOOKS-scored when it is
    discovered as its own capability. An empty-finding capability aggregates to
    100/green (`aggregate_score([])`).
    """
    from app.scan.rubric import by_kind

    rules = by_kind(cap.kind)
    findings, skipped = _evaluate_rules(rules, cap.file_subset, rubric_version)
    sub_scores, breakdown, aggregate, tier = aggregate_score(findings)
    result = ScanResult(
        findings=findings,
        sub_scores=sub_scores,
        score_breakdown=breakdown,
        aggregate_score=aggregate,
        tier=tier,
        file_count=len(cap.file_subset),
        skipped_rules=skipped,
        skipped_files=[],
        ref_sha=ref_sha,
        latency_ms=0,
        files_index=list(cap.file_subset),
    )
    return CapabilityResult(
        kind=cap.kind,
        name=cap.name,
        component_path=cap.component_path,
        result=result,
    )


def _score_file_index(
    file_index: list[tuple[str, bytes]],
    rubric_version: str,
    ref_sha: str,
) -> tuple[list[CapabilityResult], int, str, dict[str, int]]:
    """Discover + score a file index into (scored caps, repo aggregate, tier, tally).

    The source-agnostic core shared by `run_repo_scan` (GitHub) and
    `run_repo_scan_from_index` (upload). No I/O, no timing — callers own those —
    so the GitHub path stays byte-identical (same discover/score/aggregate calls,
    same order).
    """
    from app.scan.discovery import discover_capabilities

    capabilities = discover_capabilities(file_index)
    if not capabilities:  # discovery guarantees ≥1; defensive belt-and-braces.
        raise RuntimeError("discovery returned zero capabilities")

    scored = [score_capability(cap, rubric_version, ref_sha) for cap in capabilities]

    scores = [c.result.aggregate_score for c in scored]
    repo_aggregate = round(sum(scores) / len(scores))
    repo_tier = tier_for(repo_aggregate)

    kind_tally: dict[str, int] = {}
    for cap in scored:
        kind_tally[cap.kind] = kind_tally.get(cap.kind, 0) + 1

    return scored, repo_aggregate, repo_tier, kind_tally


async def run_repo_scan(
    github_url: str,
    rubric_version: str,
) -> RepoScanResult:
    """Scan a repo: fetch once, discover capabilities, score each independently.

    The repo aggregate is the mean of the per-capability aggregate scores. Every
    repo yields ≥1 capability (the discovery layer's whole-repo fallback), so a
    plain single-artifact repo stays 1:1 with today's behaviour.
    """
    started = time.monotonic()
    result = await fetch.fetch_repository(github_url)
    file_index: list[tuple[str, bytes]] = list(fetch.walk_files(result.directory))

    scored, repo_aggregate, repo_tier, kind_tally = _score_file_index(
        file_index, rubric_version, result.ref_sha
    )

    latency_ms = int((time.monotonic() - started) * 1000)

    return RepoScanResult(
        capabilities=scored,
        repo_aggregate_score=repo_aggregate,
        repo_tier=repo_tier,
        kind_tally=kind_tally,
        capability_count=len(scored),
        ref_sha=result.ref_sha,
        file_count=result.file_count,
        latency_ms=latency_ms,
        skipped_files=result.skipped_oversized_files,
    )


def run_repo_scan_from_index(
    file_index: list[tuple[str, bytes]],
    rubric_version: str,
    *,
    ref_sha: str = "0" * 40,
) -> RepoScanResult:
    """Scan a pre-extracted in-memory file index (the upload front-end, I-3.5).

    The engine is source-agnostic: an uploaded artifact produces the identical
    `list[(path, bytes)]` index the GitHub fetch path produces, so discovery →
    scoring → aggregation are unchanged. `ref_sha` defaults to the 40-zero
    sentinel (uploads have no git ref). Synchronous — no fetch, no I/O.
    """
    started = time.monotonic()
    scored, repo_aggregate, repo_tier, kind_tally = _score_file_index(
        file_index, rubric_version, ref_sha
    )
    latency_ms = int((time.monotonic() - started) * 1000)

    return RepoScanResult(
        capabilities=scored,
        repo_aggregate_score=repo_aggregate,
        repo_tier=repo_tier,
        kind_tally=kind_tally,
        capability_count=len(scored),
        ref_sha=ref_sha,
        file_count=len(file_index),
        latency_ms=latency_ms,
        skipped_files=[],
    )
