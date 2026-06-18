"""Explainable-finding prose sub-models, inlined into each report finding.

`RuleSaferPattern` / `RuleRemediation` / `RuleContent` describe the plain-English
content for one `rule_id` (title / explanation / remediation / …). They are
loaded from `app/generated/rule_content.json` (codegen step 7, emitted from the
SAME `rubric/**` frontmatter that produces the webapp `content.ts`) by
`app/services/rule_prose.py` and folded onto each `FindingResponse` server-side —
so the client renders finding prose straight from the scan/item report it already
holds, only for the rules that actually fired (rules are evaluated online, the
CLI never carries the rule corpus).

Relocated verbatim from the deleted `app/schemas/rubric.py` (the
`GET /api/v1/rubric/content` endpoint is gone). These are report-DTO-only and
mirror the `evidence_excerpt` contract — never persisted on `findings`, never in
the scan trace.
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
