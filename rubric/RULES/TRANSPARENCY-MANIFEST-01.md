---
ruleId: SS-RULES-TRANSPARENCY-MANIFEST-01
severity: medium
subScore: transparency
weight: 12
status: active
shadowUntil: null
appliesTo: [rules]
trigger:
  type: file_glob_absent
  paths: ['README.md', 'README', '.cursor/rules/README.md', '.windsurf/rules/README.md']
limitations:
  - "A README at repo root satisfies the rule even if the rules subdirectory itself is undocumented. Subdirectory-specific documentation is a future v2 refinement."
  - "Cannot validate README content quality."
priorArt:
  - https://docs.cursor.com/context/rules-for-ai
  - https://docs.windsurf.com/windsurf/cascade/memories
---

# SS-RULES-TRANSPARENCY-MANIFEST-01 — Missing rules-set documentation

## Rationale

A Cursor / Windsurf / Continue rules repository without a README is an
opaque rules set — consumers cannot determine the intent, scope, or
behaviour of the rules without reading every rule file. Transparency
sub-score impact mirrors the SKILL-equivalent rule.

Medium severity, active at landing — zero-FP file-presence check.

## False positive history

(date-stamped log; updated by FP-audit harness and vendor-appeal outcomes)

## Version history

- v1 (Phase A 2026-W2): initial rule. Active at landing.
