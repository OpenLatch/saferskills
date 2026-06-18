---
ruleId: SS-RULES-TRANSPARENCY-MANIFEST-01
severity: medium
subScore: transparency
weight: 12
status: active
shadowUntil: null
appliesTo: [rules]
title: >-
  Rules set ships without a README
categoryLabel: >-
  Transparency
explanation: >-
  This rules repository has no README. Because rule files are injected verbatim into the agent's
  context, an undocumented set forces consumers to read every file to learn its intent, scope, and
  behaviour — making hidden or surprising instructions easy to miss.
severityRationale: >-
  without documentation, consumers cannot judge what the rules inject before adopting them.
remediation:
  action: >-
    Add a README that explains what the rules set does, its scope, and any behaviour it imposes on the agent.
  steps:
    - >-
      Create a README at the repo root or beside the rules directory describing each rule's intent and scope.
    - >-
      Note any instruction that changes the agent's default behaviour so adopters can review it without opening every file.
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

- v1 (2026-01-09): initial rule. Active at landing.
