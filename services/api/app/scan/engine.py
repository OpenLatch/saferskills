"""Generic detector runtime.

Three trigger types fire in the static-detection engine:

- `regex_match` — compile the rule's pattern (with flags), scan every file
  whose path matches the rule's `trigger.scope.paths` glob list. Each match
  yields one Finding pinned to (file_path, line_start, matched_content_sha256).
- `file_glob_absent` — for each pattern in `trigger.absentPaths`, if NO file
  matches, fire one Finding pinned to that pattern.
- `metadata_check` — for each pattern in `trigger.fileGlob`, parse JSON/YAML,
  evaluate `trigger.predicate` against the resulting dict. The engine supports
  the `missing_field` and `field_equals` predicates.

`commit_history_check` and `composite_and_or` rules are recognised but the
engine does NOT fire them — they are reported as `skipped_rules` on the
ScanResult so the queue worker can emit a per-stage NOTICE that surfaces in
the SSE progress feed.

Scoring follows the rubric `scan-report.schema.json` contract:

- Each finding contributes `penalty` (clamped 0-40) to its sub-score.
- `raw_sub_score = max(0, 100 - sum(penalties))`.
- If any contributing finding has severity=critical: `final_sub_score = min(raw, 20)`.
- Aggregate = sum of (final_sub_score * weight) where weights are
  35 / 20 / 15 / 15 / 15 (security / supply_chain / maintenance /
  transparency / community).
- **Severity ceiling**: a single ACTIVE critical caps the whole aggregate at
  ≤15, a high at ≤45, so a security failure can't be diluted by the 65%
  non-security weight. `info` + `shadow` findings never trigger it. The repo
  rollup applies the same ceiling over the union of every capability's findings.
- Tier: ≥80 green, ≥60 yellow, ≥40 orange, <40 red.
"""

from __future__ import annotations

import fnmatch
import hashlib
import json
import re
import shutil
import time
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import yaml

from app.scan import fetch
from app.scan.rubric import RULES, RubricRule, SubScore

if TYPE_CHECKING:
    from app.scan.discovery import Capability

# Severity → penalty mapping. `info` is advisory (weight 0).
SEVERITY_PENALTY: dict[str, int] = {
    "info": 0,
    "low": 5,
    "medium": 12,
    "high": 25,
    "critical": 40,
}

# Aggregate severity ceiling.
# A single ACTIVE high/critical finding caps the WHOLE aggregate, so a security
# failure is never diluted by good docs/community. info + shadow never trigger it.
SEVERITY_CEILING: dict[str, int] = {"critical": 15, "high": 45}


def _severity_ceiling(findings: list[EngineFinding]) -> int | None:
    """Lowest ceiling implied by the worst ACTIVE finding (shadow + info ignored)."""
    caps = [
        SEVERITY_CEILING[f.severity]
        for f in findings
        if f.status_at_scan == "active" and f.severity in SEVERITY_CEILING
    ]
    return min(caps) if caps else None


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
    install_spec: dict[str, Any] | None = None


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


@dataclass
class _PreparedRegex:
    """A regex rule pre-compiled once, evaluated per file in the shared file loop."""

    rule: RubricRule
    pattern: re.Pattern[str]
    scope_paths: list[str]
    penalty: int


@dataclass
class _PreparedMetadata:
    """A metadata rule with its glob/predicate extracted once."""

    rule: RubricRule
    file_glob: str
    predicate: dict[str, Any]
    penalty: int


def _prepare_regex(rule: RubricRule) -> _PreparedRegex | None:
    """Compile a regex rule's trigger once. None = the rule yields no findings
    (missing pattern / bad regex) — same silent-drop semantics as before."""
    trigger = rule.trigger
    pattern_str = trigger.get("pattern")
    if not pattern_str:
        return None
    flags = re.MULTILINE
    if "i" in str(trigger.get("flags", "")).lower():
        flags |= re.IGNORECASE
    if "s" in str(trigger.get("flags", "")).lower():
        flags |= re.DOTALL
    try:
        pattern = re.compile(pattern_str, flags=flags)
    except re.error:
        return None
    return _PreparedRegex(
        rule=rule,
        pattern=pattern,
        scope_paths=trigger.get("scope", {}).get("paths", []),
        penalty=SEVERITY_PENALTY.get(rule.severity, 0),
    )


def _prepare_metadata(rule: RubricRule) -> _PreparedMetadata | None:
    """Extract a metadata rule's glob + predicate once. None = no findings
    (missing glob/predicate) — same silent-drop semantics as before."""
    trigger = rule.trigger
    file_glob = trigger.get("fileGlob")
    predicate = trigger.get("predicate", {})
    if not file_glob or not predicate:
        return None
    return _PreparedMetadata(
        rule=rule,
        file_glob=file_glob,
        predicate=predicate,
        penalty=SEVERITY_PENALTY.get(rule.severity, 0),
    )


def _regex_findings_for_file(
    prepared: _PreparedRegex, file_path: str, text: str, rubric_version: str
) -> list[EngineFinding]:
    """Finding construction moved verbatim from the old per-rule loop — same
    line math, same sha inputs, same field order."""
    findings: list[EngineFinding] = []
    for match in prepared.pattern.finditer(text):
        matched_text = match.group(0)
        line_start = text[: match.start()].count("\n") + 1
        line_end = line_start + matched_text.count("\n") or None
        matched_sha = hashlib.sha256(matched_text.encode("utf-8")).hexdigest()
        findings.append(
            EngineFinding(
                rule_id=prepared.rule.rule_id,
                severity=prepared.rule.severity,
                sub_score=prepared.rule.sub_score,
                penalty=prepared.penalty,
                status_at_scan=prepared.rule.status,
                file_path=file_path,
                line_start=line_start,
                line_end=line_end,
                matched_content_sha256=matched_sha,
                remediation_link=prepared.rule.remediation_link,
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


# Sentinel: the file's structured parse failed (or isn't JSON/YAML) — cached so
# a 2nd metadata rule on the same file doesn't re-attempt the parse.
_PARSE_FAILED = object()


def _parse_structured(file_path: str, text: str) -> Any:
    """Parse a JSON/YAML file once. Returns `_PARSE_FAILED` for a non-structured
    extension or a parse error — exactly the cases the old per-rule loop
    `continue`d on."""
    if file_path.endswith((".json",)):
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return _PARSE_FAILED
    if file_path.endswith((".yaml", ".yml")):
        try:
            return yaml.safe_load(text)
        except yaml.YAMLError:
            return _PARSE_FAILED
    return _PARSE_FAILED


def _metadata_finding_for_file(
    prepared: _PreparedMetadata, file_path: str, parsed: Any, rubric_version: str
) -> EngineFinding | None:
    """Finding construction moved verbatim from the old per-rule loop."""
    if not _predicate_holds(prepared.predicate, parsed):
        return None
    target_field = prepared.predicate.get("field", "<root>")
    marker = hashlib.sha256(f"{file_path}:{target_field}".encode()).hexdigest()
    return EngineFinding(
        rule_id=prepared.rule.rule_id,
        severity=prepared.rule.severity,
        sub_score=prepared.rule.sub_score,
        penalty=prepared.penalty,
        status_at_scan=prepared.rule.status,
        file_path=file_path,
        line_start=1,
        line_end=None,
        matched_content_sha256=marker,
        remediation_link=prepared.rule.remediation_link,
        rubric_version=rubric_version,
    )


def _predicate_holds(predicate: dict[str, Any], parsed: Any) -> bool:
    """Evaluate a metadata-check predicate. The engine supports two ops:

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

    Memory-aware shape: rules are PREPARED once (compiled regex / extracted
    predicate), then the file loop runs OUTER — each file is decoded at most
    once and JSON/YAML-parsed at most once (failure cached), shared by every
    content rule, instead of the old rules-outer loop re-decoding the whole
    index per rule (~N_rules x index decode churn). Findings are bucketed per
    rule and emitted in the original rule order, so the output list is
    byte-identical to the old per-rule iteration (per rule → per in-scope file
    → per match).
    """
    skipped: list[str] = []
    # (trigger_type, rule) in original order — the emit order.
    ordered: list[tuple[str, RubricRule]] = []
    regex_rules: list[_PreparedRegex] = []
    metadata_rules: list[_PreparedMetadata] = []

    for rule in rules:
        if sub_score_filter is not None and rule.sub_score != sub_score_filter:
            continue
        if not rule.is_directly_evaluable:
            skipped.append(rule.rule_id)
            continue
        if rule.trigger_type == "regex_match":
            prepared_re = _prepare_regex(rule)
            if prepared_re is not None:
                regex_rules.append(prepared_re)
            ordered.append((rule.trigger_type, rule))
        elif rule.trigger_type == "file_glob_absent":
            ordered.append((rule.trigger_type, rule))
        elif rule.trigger_type == "metadata_check":
            prepared_md = _prepare_metadata(rule)
            if prepared_md is not None:
                metadata_rules.append(prepared_md)
            ordered.append((rule.trigger_type, rule))

    # File loop — decode/parse each file at most once, run every content rule.
    per_rule: dict[str, list[EngineFinding]] = {}
    if regex_rules or metadata_rules:
        for file_path, content in file_index:
            text: str | None = None  # decoded lazily, at most once per file
            parsed: Any = None
            parsed_ready = False
            for pr in regex_rules:
                if pr.scope_paths and not _match_any_glob(file_path, pr.scope_paths):
                    continue
                if text is None:
                    text = content.decode("utf-8", errors="replace")
                hits = _regex_findings_for_file(pr, file_path, text, rubric_version)
                if hits:
                    per_rule.setdefault(pr.rule.rule_id, []).extend(hits)
            for pm in metadata_rules:
                if not _match_any_glob(file_path, [pm.file_glob]):
                    continue
                if not parsed_ready:
                    parsed_ready = True
                    if file_path.endswith((".json", ".yaml", ".yml")):
                        if text is None:
                            text = content.decode("utf-8", errors="replace")
                        parsed = _parse_structured(file_path, text)
                    else:
                        parsed = _PARSE_FAILED
                if parsed is _PARSE_FAILED:
                    continue
                finding = _metadata_finding_for_file(pm, file_path, parsed, rubric_version)
                if finding is not None:
                    per_rule.setdefault(pm.rule.rule_id, []).append(finding)

    # Emit in original rule order — byte-identical to the old per-rule loop.
    findings: list[EngineFinding] = []
    for trigger_type, rule in ordered:
        if trigger_type == "file_glob_absent":
            findings.extend(_evaluate_file_glob_absent(rule, file_index, rubric_version))
        else:
            findings.extend(per_rule.get(rule.rule_id, []))
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
        final = min(raw, 20) if critical_floor else raw
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

    weighted_aggregate = round(weighted_total)
    ceiling = _severity_ceiling(findings)
    aggregate = min(weighted_aggregate, ceiling) if ceiling is not None else weighted_aggregate
    tier = tier_for(aggregate)

    breakdowns["aggregate_math"] = {
        "formula": " + ".join(formula_parts),
        "weighted_contributions": weights_used,
        "tier_mapping": f"aggregate {aggregate} → tier {tier}",
        "severity_ceiling": {
            "ceiling": ceiling,
            "weighted_aggregate": weighted_aggregate,
            "applied": ceiling is not None and aggregate < weighted_aggregate,
        },
    }

    return sub_scores, breakdowns, aggregate, tier


def _walk_and_cleanup(result: fetch.FetchResult) -> tuple[list[tuple[str, bytes]], list[str]]:
    """Read the bounded file index into memory, then drop the temp tree.

    Returns `(file_index, over_bounds_skipped)`. The walk streams files in
    sorted-path order through `collect_bounded_index`, so the in-memory index is
    capped at the per-repo budget (`scan_max_index_files` /
    `scan_max_index_total_bytes`) — the 25 MiB tarball cap bounds only the
    COMPRESSED stream, and an uncompressed text repo could otherwise be 100s of
    MB in RAM. Cleanup runs in a `finally` so the temp tree never leaks (the
    durable bulk drain would otherwise fill `/tmp`).
    """
    try:
        return fetch.collect_bounded_index(fetch.walk_files(result.directory))
    finally:
        shutil.rmtree(result.directory, ignore_errors=True)


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
    file_index, over_bounds = _walk_and_cleanup(result)

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
        skipped_files=result.skipped_oversized_files + over_bounds,
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
        install_spec=cap.install_spec,
    )


def _score_file_index(
    file_index: list[tuple[str, bytes]],
    rubric_version: str,
    ref_sha: str,
    *,
    source_kind: str | None = None,
) -> tuple[list[CapabilityResult], int, str, dict[str, int]]:
    """Discover + score a file index into (scored caps, repo aggregate, tier, tally).

    The source-agnostic core shared by `run_repo_scan` (GitHub) and
    `run_repo_scan_from_index` (upload). No I/O, no timing — callers own those —
    so the GitHub path stays byte-identical (same discover/score/aggregate calls,
    same order). `source_kind` is forwarded to discovery so a flat upload fans
    its top-level files into per-file capabilities; GitHub passes None.
    """
    from app.scan.discovery import discover_capabilities

    capabilities = discover_capabilities(file_index, source_kind=source_kind)
    if not capabilities:  # discovery guarantees ≥1; defensive belt-and-braces.
        raise RuntimeError("discovery returned zero capabilities")

    scored = [score_capability(cap, rubric_version, ref_sha) for cap in capabilities]

    scores = [c.result.aggregate_score for c in scored]
    repo_aggregate = round(sum(scores) / len(scores))
    # Mirror the per-capability severity ceiling over the union of all capability
    # findings, so one dangerous capability can't be diluted back up by clean ones.
    repo_ceiling = _severity_ceiling([f for c in scored for f in c.result.findings])
    if repo_ceiling is not None:
        repo_aggregate = min(repo_aggregate, repo_ceiling)
    repo_tier = tier_for(repo_aggregate)

    kind_tally: dict[str, int] = {}
    for cap in scored:
        kind_tally[cap.kind] = kind_tally.get(cap.kind, 0) + 1

    return scored, repo_aggregate, repo_tier, kind_tally


def _assemble_repo_scan_result(
    file_index: list[tuple[str, bytes]],
    rubric_version: str,
    ref_sha: str,
    *,
    skipped_files: list[str],
    started: float,
    source_kind: str | None = None,
) -> RepoScanResult:
    """Discover + score a file index into a `RepoScanResult` (the shared tail).

    The single source-agnostic core the three `run_repo_scan*` entry points
    converge on once their bytes are in hand — so scoring, aggregation, latency,
    and result shape can't drift between the tarball / trees / upload paths.
    Caller owns `started` (what's inside the latency window differs per path).
    """
    scored, repo_aggregate, repo_tier, kind_tally = _score_file_index(
        file_index, rubric_version, ref_sha, source_kind=source_kind
    )
    return RepoScanResult(
        capabilities=scored,
        repo_aggregate_score=repo_aggregate,
        repo_tier=repo_tier,
        kind_tally=kind_tally,
        capability_count=len(scored),
        ref_sha=ref_sha,
        file_count=len(file_index),
        latency_ms=int((time.monotonic() - started) * 1000),
        skipped_files=skipped_files,
    )


async def run_repo_scan(
    github_url: str,
    rubric_version: str,
) -> RepoScanResult:
    """Scan a repo: fetch once (tarball), discover capabilities, score each.

    The repo aggregate is the mean of the per-capability aggregate scores. Every
    repo yields ≥1 capability (the discovery layer's whole-repo fallback), so a
    plain single-artifact repo stays 1:1 with today's behaviour.
    """
    started = time.monotonic()
    result = await fetch.fetch_repository(github_url)
    file_index, over_bounds = _walk_and_cleanup(result)
    return _assemble_repo_scan_result(
        file_index,
        rubric_version,
        result.ref_sha,
        skipped_files=result.skipped_oversized_files + over_bounds,
        started=started,
    )


async def run_repo_scan_via_trees(
    github_url: str,
    rubric_version: str,
    *,
    ref_sha: str,
    default_branch: str,
) -> RepoScanResult:
    """Large-repo scan path: list the tree (1 REST call) + fetch only the
    ≤ 5 MiB blobs from `raw.githubusercontent.com`, bypassing the 25 MiB
    single-stream tarball cap that fails monorepos / `awesome-*` collections.

    Converges on the same `_assemble_repo_scan_result` core as `run_repo_scan`,
    fed the identical file set the tarball path would keep after its > 5 MiB
    skip — so scores, snapshot, `.zip`, and `content_hash_sha256` stay
    byte-identical; only how the bytes arrive changes. `skipped_files` carries
    the trees-path skip list (oversized + any blob past the per-repo bounds).
    """
    started = time.monotonic()
    file_index, skipped = await fetch.fetch_file_index_via_trees(
        github_url, ref_sha=ref_sha, default_branch=default_branch
    )
    return _assemble_repo_scan_result(
        file_index, rubric_version, ref_sha, skipped_files=skipped, started=started
    )


def run_repo_scan_from_index(
    file_index: list[tuple[str, bytes]],
    rubric_version: str,
    *,
    ref_sha: str = "0" * 40,
    source_kind: str | None = None,
) -> RepoScanResult:
    """Scan a pre-extracted in-memory file index (the upload front-end).

    The engine is source-agnostic: an uploaded artifact produces the identical
    `list[(path, bytes)]` index the GitHub fetch path produces, so discovery →
    scoring → aggregation are unchanged. `ref_sha` defaults to the 40-zero
    sentinel (uploads have no git ref). `source_kind="upload"` lets discovery fan
    a flat upload's top-level files into per-file capabilities. Synchronous —
    no fetch, no I/O.
    """
    started = time.monotonic()
    return _assemble_repo_scan_result(
        file_index,
        rubric_version,
        ref_sha,
        skipped_files=[],
        started=started,
        source_kind=source_kind,
    )
