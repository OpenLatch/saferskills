---
ruleId: SS-SKILL-TRANSPARENCY-DESCRIPTION-01
severity: low
subScore: transparency
weight: 5
status: active
shadowUntil: null
appliesTo: [skill, mcp, rules, hooks, plugin]
trigger:
  type: file_glob_absent
  paths: ['README.md', 'README', 'README.rst', 'README.txt']
limitations:
  - "Does not assess README quality, length, or accuracy. A one-line README satisfies the rule."
  - "Cannot consult repository-description-only documentation (GitHub repo description with no README file). v2 may treat a non-empty GitHub repo description as partial credit."
priorArt:
  - https://opensource.guide/starting-a-project/
  - https://github.com/ossf/scorecard/blob/main/docs/checks.md#packaging
---

# SS-SKILL-TRANSPARENCY-DESCRIPTION-01 — Missing README

## Rationale

A README file is the canonical documentation entry point for any open-source
artifact. Without one, a prospective consumer cannot understand the
artifact's purpose without reading source code or executing it speculatively
— both unacceptable risks for skills that auto-install into agent contexts.

The rule is intentionally low-severity (weight 5) and detects presence only —
quality is not assessed. Even a single-line README satisfies it. The
operational outcome is binary: documented vs. opaque.

Active at landing under the same zero-FP file-presence justification as the
other Transparency rules. The cumulative effect of the five Transparency
rules in this batch (manifest, license, changelog, security, readme) on an
undocumented repository is a meaningful Transparency sub-score reduction
without any single rule being heavy-handed.

## False positive history

(date-stamped log; updated by FP-audit harness and vendor-appeal outcomes)

## Version history

- v1 (Phase A 2026-W2): initial rule. Active at landing.
