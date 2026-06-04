"""Wire types for GET /api/v1/rubric/content — offline finding prose (D-05-32).

The install CLI fetches this map once, caches it under `~/.saferskills/cache/`,
and renders finding explanations (title / explanation / remediation) offline so
a `saferskills install` gate reads as defensible fact, not opinion.

The payload is loaded verbatim from `app/generated/rule_content.json`, which the
methodology generator (codegen step 7) emits from the SAME `rubric/**` frontmatter
that produces `webapp/src/generated/rules/content.ts` — the two can never drift.
Hand-written endpoint DTO (non-generated wrapper) per
`.claude/rules/schema-driven-development.md` § "Adding a new endpoint DTO".
"""

from __future__ import annotations

from app.schemas.orm_base import OrmBaseModel


class RuleSaferPattern(OrmBaseModel):
    """Optional Avoid → Safer before/after pair for a remediation."""

    before: str
    after: str


class RuleRemediation(OrmBaseModel):
    """How to fix a finding. `action` is always present; the rest are optional."""

    action: str
    steps: list[str] | None = None
    safer_pattern: RuleSaferPattern | None = None


class RuleContent(OrmBaseModel):
    """Plain-English content for one rule_id (no rule_id-specific PII)."""

    rule_id: str
    severity: str
    sub_score: str
    category_label: str
    title: str
    explanation: str
    severity_rationale: str | None = None
    remediation: RuleRemediation


class RubricContentResponse(OrmBaseModel):
    """`{rubric_version, rules}` — the full explainable-finding content map.

    `rubric_version` is the content-addressable git tree SHA of `rubric/`; the CLI
    keys its cache on it and refetches only when it changes.
    """

    rubric_version: str
    rules: dict[str, RuleContent]
