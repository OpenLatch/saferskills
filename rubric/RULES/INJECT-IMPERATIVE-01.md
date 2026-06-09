---
ruleId: SS-RULES-INJECT-IMPERATIVE-01
severity: medium
subScore: security
weight: 15
status: shadow
shadowUntil: 2026-W3-end
appliesTo: [rules]
frameworks: ["owasp-llm:llm01", "mitre-atlas:AML.T0051"]
title: >-
  Rules file commands the agent to hide or withhold information
categoryLabel: >-
  Prompt injection
explanation: >-
  A rules file is loaded verbatim into the agent as standing instructions for every session. A
  non-disclosure imperative like {match} steers the agent to conceal behaviour, hide tool calls, or
  withhold information on every prompt — never appearing in any single conversation you'd review.
severityRationale: >-
  the instruction reshapes the agent's disclosure behaviour silently across every session, not one prompt.
remediation:
  action: >-
    Remove the non-disclosure imperative, or restate it as a neutral confidentiality guideline scoped to data, not the agent's honesty.
  steps:
    - >-
      Delete or reword the highlighted instruction so it describes a data-handling boundary (e.g. "keep secrets out of logs") rather than commanding the agent to hide its actions.
    - >-
      Confirm no remaining rule tells the agent to lie about, conceal, or refuse to disclose its own behaviour.
trigger:
  type: regex_match
  pattern: '(?im)^\s*(?:•|-|\*|\d+\.)\s*(?:always|never|must|do\s+not|don[’'']t|under\s+no\s+circumstances)\s+(?:reveal|disclose|share|leak|tell\s+(?:the\s+)?(?:user|anyone)|mention)\b'
  scope:
    paths: ['.cursorrules', '.cursor/rules/**', '.windsurfrules', '.windsurf/rules/**', '.continuerules', 'CONTINUE.md', '**/rules.md', '**/RULES.md']
limitations:
  - "Cursor / Windsurf rule files frequently contain legitimate confidentiality instructions ('always keep API keys out of logs'). Shadow window measures FP rate."
  - "Cannot distinguish user-facing imperatives (legitimate) from model-facing imperatives (suspicious)."
priorArt:
  - https://docs.cursor.com/context/rules-for-ai
  - https://docs.windsurf.com/windsurf/cascade/memories
  - https://genai.owasp.org/llmrisk/llm01-prompt-injection/
---

# SS-RULES-INJECT-IMPERATIVE-01 — Non-disclosure imperative in rules file

## Rationale

Cursor's `.cursorrules`, Windsurf's `.windsurfrules`, and Continue's
`CONTINUE.md` are project-level rule files that the IDE injects into every
LLM prompt. An adversarial rule that instructs the consuming LLM to never
disclose specific information, lie about behaviour, or hide tool calls is
the rules-equivalent of the SKILL-INJECT-IMPERATIVE class (cf.
SS-SKILL-INJECT-IMPERATIVE-01).

The FP surface in rules files is higher than in skill bodies because rules
files legitimately contain operational guidance about disclosure boundaries
(don't log secrets, don't include credentials in error messages). Shadow
window will quantify the cost.

Medium severity matches the SKILL sibling rule.

## False positive history

(date-stamped log; updated by FP-audit harness and vendor-appeal outcomes)

## Version history

- v1 (Phase A 2026-W2): initial rule. Lands shadow; FP-audit gates promotion.
