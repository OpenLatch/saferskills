---
ruleId: SS-SKILL-INJECT-ZWSP-01
severity: high
subScore: security
weight: 25
status: active
shadowUntil: null
appliesTo: [skill, mcp, rules, hooks, plugin]
trigger:
  type: regex_match
  pattern: '[\u{200B}-\u{200D}\u{2060}\u{FEFF}]'
  flags: u
  scope:
    paths: ['**/*.md', '**/*.yaml', '**/*.yml', '**/*.json', '**/SKILL.md']
  requiresCount: 3
limitations:
  - "Requires ≥3 zero-width characters to fire (FP reduction). A single zero-width space — e.g. a copy-paste artifact from a Slack message — does not trigger."
  - "Cannot detect zero-width characters re-encoded as numeric entities (`&#x200B;`); rule operates on decoded text only."
  - "Does not currently distinguish between zero-width characters used legitimately in CJK script and the same characters used adversarially."
priorArt:
  - https://embracethered.com/blog/posts/2023/llm-tricks-zero-width-characters/
  - https://genai.owasp.org/llmrisk/llm01-prompt-injection/
  - https://www.unicode.org/reports/tr36/
---

# SS-SKILL-INJECT-ZWSP-01 — Zero-width character smuggling

## Rationale

Zero-width characters (U+200B Zero-Width Space, U+200C Zero-Width Non-Joiner,
U+200D Zero-Width Joiner, U+2060 Word Joiner, U+FEFF Zero-Width No-Break Space)
are invisible in normal renderers but, like the plane-14 tag channel, are
emitted as distinct tokens by LLM tokenizers. They are the lower-impact cousin
of Unicode tag-channel smuggling (SS-SKILL-INJECT-UNICODE-TAG-01) because they
can occasionally appear legitimately as artifacts of copy-paste from chat
applications, as ligature controls in CJK script, or as byte-order markers at
file heads. We therefore use a higher false-positive bar: the rule fires only
when ≥3 zero-width characters are present in a file in scope, a threshold
empirically chosen to suppress incidental contamination while still catching
the deliberate injection pattern documented in Embrace the Red's 2023
research and the OWASP LLM Top 10 2025 LLM01 indirect-injection guidance.

`high` severity (rather than `critical`) reflects the lower-but-real impact:
the attack vector is identical to tag-channel smuggling, but the FP-noise floor
is non-zero, making aggressive scoring inappropriate. A 25-point penalty
against a 35-point sub-score weight still pushes a finding repo two
tier-bands lower, which matches the operational severity.

When this rule fires alongside SS-SKILL-INJECT-UNICODE-TAG-01 on the same
artifact, the critical-floor cap (sub_score ≤ 40 if any critical finding) takes
precedence; the zero-width finding remains in the public trace as supporting
evidence but does not double-count.

## False positive history

(date-stamped log; updated by FP-audit harness and vendor-appeal outcomes)

## Version history

- v1 (Phase A 2026-W2): initial rule. Active at landing with requiresCount=3 threshold.
