---
ruleId: SS-SKILL-INJECT-EMOJI-SMUG-01
severity: medium
subScore: security
weight: 15
status: shadow
shadowUntil: 2026-W3-end
appliesTo: [skill, mcp, rules, hooks, plugin]
frameworks: ["owasp-llm:llm01", "mitre-atlas:AML.T0051"]
title: >-
  Long emoji run that may be smuggling a hidden instruction
categoryLabel: >-
  Obfuscation
explanation: >-
  Long runs of emoji — especially with variation selectors and zero-width joiners —
  tokenize in model-specific ways that can encode an instruction while reading as harmless
  decoration to a person. This rule flags ten or more consecutive emoji, a length that is
  rare in genuine documentation but common in this obfuscation technique.
severityRationale: >-
  the technique works but is brittle and tokenizer-dependent, so the practical attack surface is narrow.
remediation:
  action: >-
    Trim the emoji run to a few decorative characters, or remove it if it is not intentional.
  steps:
    - >-
      Reduce any run of ten-plus emoji to the small set you actually meant to display.
    - >-
      Strip the variation selectors (U+FE0F) and zero-width joiners (U+200D) unless a specific emoji genuinely requires them.
trigger:
  type: regex_match
  pattern: '(?u)(?:[\U0001F300-\U0001F9FF☀-➿]\u{FE0F}?\u{200D}?){10,}'
  scope:
    paths: ['**/*.md', '**/*.yaml', '**/*.yml', '**/SKILL.md', '**/CLAUDE.md']
limitations:
  - "Cannot distinguish emoji-smuggled payloads from heavy-emoji documentation (welcome banners, decorative section dividers). Shadow window measures real-world impact."
  - "Emoji-variation-selector (FE0F) and zero-width-joiner (200D) sequences are tokenized differently across models; rule fires on the literal codepoint sequence, not on per-model token expansion."
  - "Cannot detect non-emoji obfuscation via mathematical alphanumeric symbols (U+1D400+) — that pattern is covered by SS-SKILL-INJECT-HOMOGLYPH-01."
priorArt:
  - https://embracethered.com/blog/posts/2023/llm-emoji-attacks/
  - https://genai.owasp.org/llmrisk/llm01-prompt-injection/
  - https://arxiv.org/abs/2406.14595
---

# SS-SKILL-INJECT-EMOJI-SMUG-01 — Emoji-smuggled instruction sequences

## Rationale

Emoji sequences (especially with variation selectors and zero-width joiners)
produce model-specific tokenizations that can encode instructions invisibly to
human reviewers. The 2023 research from Embrace the Red and arXiv 2406.14595
(Carlini et al., 2024) demonstrated that ≥10 consecutive emoji can carry a
meaningful tokenized payload across modern LLMs while reading as innocuous
decoration to a human. The OWASP LLM Top 10 2025 LLM01 lists this under the
broader indirect-injection vector class.

The 10-emoji threshold is empirically chosen: shorter sequences are
overwhelmingly decorative (section headers, status indicators); longer
sequences are rare in legitimate documentation and overrepresented in
adversarial samples. The shadow window will refine this threshold against
the 100-item fixture before promotion.

Medium severity reflects the relatively narrow attack surface: the technique
works but is brittle (tokenizer-dependent, more easily caught by reviewers
once awareness exists). When promoted, this rule complements (does not
duplicate) the Unicode-tag and zero-width-character rules — those cover the
canonical hidden-character classes; this covers a parallel class using
visible-but-decorative characters.

## False positive history

(date-stamped log; updated by FP-audit harness and vendor-appeal outcomes)

## Version history

- v1 (Phase A 2026-W2): initial rule. Lands shadow; FP-audit gates promotion.
