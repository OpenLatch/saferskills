---
ruleId: SS-SKILL-INJECT-IMPERATIVE-01
severity: medium
subScore: security
weight: 15
status: shadow
shadowUntil: 2026-W3-end
appliesTo: [skill, mcp, rules, hooks, plugin]
trigger:
  type: regex_match
  pattern: '(?im)^\s*(?:•|-|\*|\d+\.)\s*(?:always|never|must|do\s+not|don[’'']t|under\s+no\s+circumstances)\s+(?:reveal|disclose|share|leak|tell\s+(?:the\s+)?(?:user|anyone)|mention)\b'
  scope:
    paths: ['**/*.md', '**/SKILL.md', '**/CLAUDE.md']
limitations:
  - "FP risk is substantial: legitimate skills often contain instructions about confidentiality or scope boundaries. Shadow window measures real-world impact."
  - "Cannot detect imperative patterns expressed indirectly ('please keep X private', 'X should remain hidden') — only the strict imperative form."
  - "Does not distinguish between user-facing imperatives (legitimate) and model-facing imperatives (suspicious)."
priorArt:
  - https://genai.owasp.org/llmrisk/llm01-prompt-injection/
  - https://arxiv.org/abs/2306.05499
---

# SS-SKILL-INJECT-IMPERATIVE-01 — Strong imperative pattern

## Rationale

A subset of indirect prompt injection embeds "always X" / "never Y" / "must Z"
imperatives inside skill bodies or rule files specifically to override the
consuming model's default disclosure behaviour. The most dangerous variant
instructs the model to never disclose its tool calls, never reveal that it
followed a particular instruction, or to lie to the user about specific
behaviours. The pattern is hard to detect at line-level because the same
syntactic structure appears in legitimate skill instructions ("Always include
the API version in the request") — only the verb-noun semantics distinguish
adversarial from legitimate use.

This rule is deliberately narrow (imperative + non-disclosure verb only) but
even so the FP rate is expected to be non-trivial; we land in shadow with a
7-day FP-audit window. Promotion is contingent on <10% FP on the 100-item
fixture. The medium severity reflects both the impact uncertainty (model may
or may not honour the imperative) and the FP risk; if shadow-window data
supports promotion, the rule activates at its current weight.

A natural future extension is to chain this with a context check: an
imperative-non-disclosure pattern that appears immediately adjacent to a tool
invocation in the same skill body is materially more suspicious. That refinement
will be a v2 rule revision after the v1 FP-audit data lands.

## False positive history

(date-stamped log; updated by FP-audit harness and vendor-appeal outcomes)

## Version history

- v1 (Phase A 2026-W2): initial rule. Lands shadow; FP-audit gates promotion.
