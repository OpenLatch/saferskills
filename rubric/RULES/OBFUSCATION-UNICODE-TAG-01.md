---
ruleId: SS-RULES-OBFUSCATION-UNICODE-TAG-01
severity: critical
subScore: security
weight: 35
status: active
shadowUntil: null
appliesTo: [rules]
frameworks: ["owasp-llm:llm01", "mitre-atlas:AML.T0051"]
title: >-
  Rules file hides instructions in invisible Unicode tag characters
categoryLabel: >-
  Obfuscation
explanation: >-
  A rules file is injected verbatim into every agent prompt. Unicode tag-channel codepoints like {match}
  render as nothing to a human reviewer but are tokenized as text by the model — so hidden instructions
  steer every session while staying invisible in any editor or diff.
severityRationale: >-
  invisible-to-human instructions execute on every prompt with no review surface, the highest-trust injection path.
remediation:
  action: >-
    Remove the invisible Unicode tag characters from the rules file and keep all instructions in visible text.
  steps:
    - >-
      Strip every codepoint in the U+E0000–U+E007F tag block from the file; rewrite any intended instruction as plain visible text.
    - >-
      Re-inspect the file with a tool that reveals non-printing characters to confirm none remain.
trigger:
  type: regex_match
  pattern: '[\u{E0000}-\u{E007F}]'
  flags: u
  scope:
    paths: ['.cursorrules', '.cursor/rules/**', '.windsurfrules', '.windsurf/rules/**', '.continuerules', 'CONTINUE.md', '**/rules.md', '**/RULES.md']
limitations:
  - "Cannot detect tag-channel characters re-encoded as numeric entities."
  - "Cannot detect tag-channel chars in dynamically-loaded rules (e.g. rules constructed at IDE-runtime)."
priorArt:
  - https://aws.amazon.com/blogs/security/defending-llm-applications-against-unicode-character-smuggling/
  - https://embracethered.com/blog/posts/2024/hiding-and-finding-text-with-unicode-tags/
  - https://docs.cursor.com/context/rules-for-ai
---

# SS-RULES-OBFUSCATION-UNICODE-TAG-01 — Unicode tag-channel obfuscation in rules file

## Rationale

Rules-files-specific instance of the Unicode tag-channel attack (parallel
to SS-SKILL-INJECT-UNICODE-TAG-01 and SS-MCP-POISON-UNICODE-TAG-01). The
attack surface in rules files is identical to the skill case: the IDE
injects the rule contents into every LLM prompt, and tag-channel
codepoints are tokenized as instructions invisible to human review.

Critical severity matches the parallel rules. Active at landing under the
same scoping-and-FP-bound justification.

## False positive history

(date-stamped log; updated by FP-audit harness and vendor-appeal outcomes)

## Version history

- v1 (Phase A 2026-W2): initial rule. Active at landing.
