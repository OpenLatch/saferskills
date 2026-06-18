---
ruleId: SS-RULES-OBFUSCATION-HOMOGLYPH-01
severity: medium
subScore: security
weight: 15
status: shadow
shadowUntil: 2026-01-18
appliesTo: [rules]
frameworks: ["owasp-llm:llm01", "mitre-atlas:AML.T0051"]
title: >-
  Rules file uses look-alike characters from another script
categoryLabel: >-
  Obfuscation
explanation: >-
  A rules file is loaded verbatim into the agent. A word like {match} mixes Cyrillic, Greek, or
  mathematical look-alike letters with Latin ones — it reads normally to you but is distinct text to
  the model, letting an instruction evade keyword review while still steering the session.
severityRationale: >-
  mixed-script words evade human and keyword review while the agent reads them as standing instructions.
remediation:
  action: >-
    Replace the look-alike characters with plain ASCII letters so the rules text reads identically to humans and the model.
  steps:
    - >-
      Retype the highlighted word using standard Latin characters, removing any Cyrillic, Greek, or mathematical-alphanumeric substitutes.
    - >-
      If the rules file legitimately needs non-Latin script, keep it in clearly-labelled prose rather than inside Latin words.
trigger:
  type: regex_match
  pattern: '[\u{0400}-\u{04FF}\u{1D400}-\u{1D7FF}\u{0370}-\u{03FF}](?:[a-zA-Z]|[\u{0400}-\u{04FF}\u{1D400}-\u{1D7FF}\u{0370}-\u{03FF}]){4,}'
  flags: u
  scope:
    paths: ['.cursorrules', '.cursor/rules/**', '.windsurfrules', '.windsurf/rules/**', '.continuerules', 'CONTINUE.md', '**/rules.md', '**/RULES.md']
limitations:
  - "FP risk on multilingual rules content (legitimate use of Greek / Cyrillic identifiers in technical documentation)."
  - "Cannot detect single-character homoglyph swaps; only mixed-script words ≥5 chars long."
  - "v2 will integrate UTS #39 confusables data."
priorArt:
  - https://www.unicode.org/reports/tr39/
  - https://www.trojansource.codes/
  - https://docs.cursor.com/context/rules-for-ai
---

# SS-RULES-OBFUSCATION-HOMOGLYPH-01 — Homoglyph confusable in rules file

## Rationale

Rules-files-specific instance of the homoglyph attack class (parallel to
SS-SKILL-INJECT-HOMOGLYPH-01). Same trigger logic, same FP control
strategy, same v2 plan to integrate UTS #39 confusables. Shadow lands for
the same FP-control reasons.

## False positive history

(date-stamped log; updated by FP-audit harness and vendor-appeal outcomes)

## Version history

- v1 (2026-01-09): initial rule. Lands shadow; FP-audit gates promotion.
