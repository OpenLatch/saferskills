# rubric/ — SaferSkills detection rules

Detection rules land under `rubric/<rule_id>.json` from W2 (Initiative I-02 / Track B). Each rule is a versioned JSON document matching `schemas/detection-rule.schema.json` (which itself lands W2).

The rule lifecycle, ID convention, and approval workflow are documented in:

- [`docs/methodology.md`](../docs/methodology.md) — public-facing summary
- [`docs/rules.md`](../docs/rules.md) — rule-ID convention + lifecycle
- [`.claude/rules/methodology.md`](../.claude/rules/methodology.md) — contributor-facing detail

## Status

**W1: empty.** First rules land via the rule-RFC process in W2.

A rule lands only after:
1. An open `.github/ISSUE_TEMPLATE/03-rule-proposal.yml` RFC
2. A 7-day public comment window
3. A maintainer accept decision
4. A PR adding `rubric/<rule_id>.json` + a unit test + a positive fixture + a negative fixture
