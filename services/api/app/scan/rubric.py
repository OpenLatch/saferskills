"""Load rubric/ rule frontmatter at module-import time.

Each `rubric/<CATEGORY>/<NAME>-NN.md` carries a YAML frontmatter that defines:
- ruleId (closed-enum per `.claude/rules/naming-conventions.md`)
- severity / subScore / weight / status
- appliesTo: which artifact kinds the rule applies to
- trigger: type + parameters (regex_match, file_glob_absent, metadata_check,
  commit_history_check, composite_and_or)
- limitations / priorArt

We load the frontmatter once and expose the dict keyed by ruleId so the engine
can iterate without re-parsing.

`commit_history_check` and `composite_and_or` rules are loaded but skipped at
detect time — the Phase B engine doesn't fetch git history or evaluate
combinators (see `.claude/rules/methodology.md`).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Literal

import yaml

from app.core.config import get_settings


def _resolve_rubric_dir() -> Path:
    """Resolve the rubric/ directory.

    Order of precedence:
    1. `settings.rubric_dir` (typed env-var read; set by Docker / Fly).
    2. Source-checkout layout: `parents[4]/rubric` from this file
       (parents[0]=scan/ parents[1]=app/ parents[2]=api/ parents[3]=services/
       parents[4]=repo root).
    3. CWD-relative `./rubric` (fallback for unusual layouts).

    The `_load_all_rules` step checks `.exists()` and returns an empty registry
    if the directory is missing, so the service still boots cleanly.
    """
    override = get_settings().rubric_dir
    if override:
        return Path(override)
    source_layout = Path(__file__).resolve().parents[4] / "rubric"
    if source_layout.exists():
        return source_layout
    return Path.cwd() / "rubric"


_RUBRIC_DIR = _resolve_rubric_dir()

# Each rule's frontmatter is delimited by lines `---` at column 0.
_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


Severity = Literal["info", "low", "medium", "high", "critical"]
SubScore = Literal["security", "supply_chain", "maintenance", "transparency", "community"]
Status = Literal["shadow", "active"]
TriggerType = Literal[
    "regex_match",
    "file_glob_absent",
    "metadata_check",
    "commit_history_check",
    "composite_and_or",
]


# Camelcase keys per the YAML frontmatter convention; snake_case at runtime.
_SUB_SCORE_NORMALIZE = {
    "security": "security",
    "supplyChain": "supply_chain",
    "supply_chain": "supply_chain",
    "maintenance": "maintenance",
    "transparency": "transparency",
    "community": "community",
}


class RubricRule:
    """A loaded rule. Engine-evaluable when `trigger_type` is regex/glob/metadata."""

    __slots__ = (
        "applies_to",
        "rubric_path",
        "rule_id",
        "severity",
        "status",
        "sub_score",
        "trigger",
        "trigger_type",
        "weight",
    )

    def __init__(self, frontmatter: dict[str, Any], rubric_path: Path) -> None:
        self.rule_id: str = frontmatter["ruleId"]
        self.severity: Severity = frontmatter["severity"]
        sub_score_raw = frontmatter.get("subScore") or frontmatter.get("sub_score", "")
        normalized = _SUB_SCORE_NORMALIZE.get(sub_score_raw)
        if normalized is None:
            raise ValueError(f"Rule {self.rule_id} has unknown subScore {sub_score_raw!r}")
        self.sub_score: SubScore = normalized  # type: ignore[assignment]
        self.weight: int = int(frontmatter.get("weight", 0))
        self.status: Status = frontmatter.get("status", "shadow")
        self.applies_to: list[str] = list(frontmatter.get("appliesTo", []))
        trigger = frontmatter.get("trigger", {})
        self.trigger_type: TriggerType = trigger.get("type", "regex_match")
        self.trigger: dict[str, Any] = trigger
        self.rubric_path = rubric_path

    @property
    def category(self) -> str:
        """`SKILL` / `MCP` / `HOOKS` / `PLUGIN` / `RULES`."""
        return self.rule_id.split("-")[1]

    @property
    def is_directly_evaluable(self) -> bool:
        """True iff the Phase B engine can fire this rule from static files."""
        return self.trigger_type in {"regex_match", "file_glob_absent", "metadata_check"}

    @property
    def remediation_link(self) -> str:
        """Public methodology URL for this rule."""
        return f"https://saferskills.ai/methodology#{self.rule_id}"


def _read_frontmatter(md_path: Path) -> dict[str, Any] | None:
    text = md_path.read_text(encoding="utf-8")
    match = _FRONTMATTER_RE.match(text)
    if match is None:
        return None
    payload: object = yaml.safe_load(match.group(1))
    if not isinstance(payload, dict):
        return None
    return dict(payload)  # type: ignore[arg-type]


def _load_all_rules() -> dict[str, RubricRule]:
    rules: dict[str, RubricRule] = {}
    if not _RUBRIC_DIR.exists():
        return rules
    for md_path in sorted(_RUBRIC_DIR.rglob("*.md")):
        # Skip rubric/README.md and any category README.
        if md_path.name.upper().startswith("README"):
            continue
        frontmatter = _read_frontmatter(md_path)
        if frontmatter is None or "ruleId" not in frontmatter:
            continue
        rule = RubricRule(frontmatter, rubric_path=md_path)
        rules[rule.rule_id] = rule
    return rules


# Loaded once at import time. Re-import for hot-reload in tests via `importlib.reload`.
RULES: dict[str, RubricRule] = _load_all_rules()


def by_sub_score(sub_score: SubScore) -> list[RubricRule]:
    """All rules contributing to the given sub-score."""
    return [r for r in RULES.values() if r.sub_score == sub_score]


def by_kind(kind: str) -> list[RubricRule]:
    """All rules whose `appliesTo` includes the given artifact kind."""
    # CatalogItem.kind uses snake_case (`mcp_server`); rubric uses short tags (`mcp`).
    aliases = {
        "skill": ["skill"],
        "mcp_server": ["mcp"],
        "hook": ["hooks"],
        "plugin": ["plugin"],
        "rules": ["rules"],
    }
    targets = aliases.get(kind, [kind])
    return [r for r in RULES.values() if any(t in r.applies_to for t in targets)]


def count_for(sub_score: SubScore) -> int:
    """Number of evaluable rules for a sub-score (used for KPI tiles)."""
    return sum(1 for r in by_sub_score(sub_score) if r.is_directly_evaluable)
