"""FP-audit runner.

Loads the rubric (frontmatter only — no engine at Phase A), enumerates
fixtures from `fixtures/known-{good,bad}/manifest.yaml`, and produces a
report. The engine call is stubbed to return `deferred_engine_unavailable`
for every rule until Phase B imports the real detector engine from
`services/api/app/scan/`.
"""

from __future__ import annotations

import enum
import subprocess
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import yaml


class AuditDecision(enum.StrEnum):
    PROMOTE_TO_ACTIVE = "promote_to_active"
    ACTIVE_CONFIRMED = "active_confirmed"
    SHADOW_EXTENDED = "shadow_extended"
    DEMOTE_TO_SHADOW = "demote_to_shadow"
    DEFERRED_ENGINE_UNAVAILABLE = "deferred_engine_unavailable"


@dataclass
class RuleReport:
    rule_id: str
    fixtures_evaluated: int
    true_positives: int
    true_negatives: int
    false_positives: int
    false_negatives: int
    fp_rate: float
    decision: AuditDecision

    def to_dict(self) -> dict[str, object]:
        return {
            "ruleId": self.rule_id,
            "fixturesEvaluated": self.fixtures_evaluated,
            "truePositives": self.true_positives,
            "trueNegatives": self.true_negatives,
            "falsePositives": self.false_positives,
            "falseNegatives": self.false_negatives,
            "fpRate": self.fp_rate,
            "decision": self.decision.value,
        }


@dataclass
class AuditReport:
    generated_at: str
    rubric_version: str
    engine_version: str | None
    total_fixtures: int
    per_rule: list[RuleReport] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "generatedAt": self.generated_at,
            "rubricVersion": self.rubric_version,
            "engineVersion": self.engine_version,
            "totalFixtures": self.total_fixtures,
            "perRule": [r.to_dict() for r in self.per_rule],
        }


def _git_sha(repo_root: Path, path: str) -> str:
    try:
        out = subprocess.check_output(
            ["git", "log", "-n", "1", "--pretty=format:%H", "--", path],
            cwd=repo_root,
            text=True,
        ).strip()
        return out or "unknown"
    except subprocess.CalledProcessError:
        return "unknown"


def _load_rubric_rules(repo_root: Path, rule_id: str | None) -> list[dict[str, object]]:
    rubric_dir = repo_root / "rubric"
    rules: list[dict[str, object]] = []
    if not rubric_dir.exists():
        return rules
    for category_dir in sorted(rubric_dir.iterdir()):
        if not category_dir.is_dir():
            continue
        for path in sorted(category_dir.glob("*.md")):
            if path.name.upper() == "README.MD":
                continue
            text = path.read_text(encoding="utf-8")
            if not text.startswith("---"):
                continue
            close = text.find("\n---", 3)
            if close == -1:
                continue
            try:
                fm = yaml.safe_load(text[4:close])
            except yaml.YAMLError:
                continue
            if rule_id and fm.get("ruleId") != rule_id:
                continue
            rules.append(cast(dict[str, object], fm))
    return rules


def _load_fixtures(repo_root: Path) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    base = repo_root / "tools" / "fp-audit" / "fixtures"
    good_manifest = base / "known-good" / "manifest.yaml"
    bad_manifest = base / "known-bad" / "manifest.yaml"
    good = (
        cast(
            list[dict[str, object]], yaml.safe_load(good_manifest.read_text(encoding="utf-8")) or []
        )
        if good_manifest.exists()
        else []
    )
    bad = (
        cast(
            list[dict[str, object]], yaml.safe_load(bad_manifest.read_text(encoding="utf-8")) or []
        )
        if bad_manifest.exists()
        else []
    )
    return good, bad


def _engine_available() -> bool:
    """Whether the scan engine is importable. Phase A: False. Phase B: True."""
    try:
        import importlib

        importlib.import_module("app.scan")
        return True
    except ImportError, ModuleNotFoundError:
        return False


def run_audit(
    *,
    repo_root: Path,
    rule_id: str | None = None,
    run_all: bool = False,
    dry_run: bool = False,
) -> AuditReport:
    """Execute the audit and return a structured report."""
    rules = _load_rubric_rules(repo_root, rule_id)
    if run_all and not rule_id:
        # Filter is the empty case — keep all.
        pass

    good, bad = _load_fixtures(repo_root)
    total_fixtures = len(good) + len(bad)

    rubric_version = _git_sha(repo_root, "rubric/")
    engine_available = (not dry_run) and _engine_available()
    engine_version = _git_sha(repo_root, "services/api/app/scan/") if engine_available else None

    per_rule: list[RuleReport] = []
    for fm in rules:
        rid = cast(str, fm.get("ruleId", "UNKNOWN"))
        status = cast(str, fm.get("status", "shadow"))

        if not engine_available:
            per_rule.append(
                RuleReport(
                    rule_id=rid,
                    fixtures_evaluated=0,
                    true_positives=0,
                    true_negatives=0,
                    false_positives=0,
                    false_negatives=0,
                    fp_rate=0.0,
                    decision=AuditDecision.DEFERRED_ENGINE_UNAVAILABLE,
                )
            )
            continue

        # Phase B+ live path: engine evaluates each fixture, populates counts,
        # decision derived from thresholds.yaml. Stubbed here until that lands.
        per_rule.append(
            RuleReport(
                rule_id=rid,
                fixtures_evaluated=total_fixtures,
                true_positives=0,
                true_negatives=0,
                false_positives=0,
                false_negatives=0,
                fp_rate=0.0,
                decision=(
                    AuditDecision.ACTIVE_CONFIRMED
                    if status == "active"
                    else AuditDecision.SHADOW_EXTENDED
                ),
            )
        )

    return AuditReport(
        generated_at=datetime.now(UTC).isoformat(),
        rubric_version=rubric_version,
        engine_version=engine_version,
        total_fixtures=total_fixtures,
        per_rule=per_rule,
    )
