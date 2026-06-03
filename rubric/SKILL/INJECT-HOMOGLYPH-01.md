---
ruleId: SS-SKILL-INJECT-HOMOGLYPH-01
severity: medium
subScore: security
weight: 15
status: shadow
shadowUntil: 2026-W3-end
appliesTo: [skill, mcp, rules, hooks, plugin]
title: >-
  Look-alike (homoglyph) characters mixed into otherwise-Latin words
categoryLabel: >-
  Obfuscation
explanation: >-
  A word can look like plain English while secretly containing Cyrillic, Greek, or
  mathematical letters that are visually identical to ASCII — Cyrillic 'а' for Latin 'a',
  Greek 'ο' for 'o'. This rule flags mixed-script words of five or more characters, a
  technique used to slip past keyword filters while reading normally to a person.
severityRationale: >-
  the swap defeats text-matching review but is neutralized by NFKC normalization at consumption, so impact is bounded.
remediation:
  action: >-
    Retype the affected words entirely in ASCII, or NFKC-normalize the file before review.
  steps:
    - >-
      Replace each non-Latin look-alike character with its plain ASCII equivalent.
    - >-
      If the document legitimately needs Cyrillic or Greek text, keep those words in a single script rather than mixing scripts inside one word.
  saferPattern:
    before: |-
      Run the аdmin install step  (the "a" here is Cyrillic U+0430)
    after: |-
      Run the admin install step  (all-ASCII)
trigger:
  type: regex_match
  pattern: '[\u{0400}-\u{04FF}\u{1D400}-\u{1D7FF}\u{0370}-\u{03FF}](?:[a-zA-Z]|[\u{0400}-\u{04FF}\u{1D400}-\u{1D7FF}\u{0370}-\u{03FF}]){4,}'
  flags: u
  scope:
    paths: ['**/*.md', '**/*.yaml', '**/*.yml', '**/*.json', '**/SKILL.md', '**/CLAUDE.md']
limitations:
  - "FP risk on multilingual documentation (Russian / Greek / mathematical) that legitimately uses non-Latin scripts. Shadow window measures the cost."
  - "Cannot detect single-character homoglyph swaps in identifiers — only mixed-script words ≥5 chars long."
  - "Does not currently consult a homoglyph-confusable table (UTS #39); a v2 revision will integrate the Unicode confusables data."
priorArt:
  - https://www.unicode.org/reports/tr39/
  - https://www.trojansource.codes/
  - https://genai.owasp.org/llmrisk/llm01-prompt-injection/
---

# SS-SKILL-INJECT-HOMOGLYPH-01 — Homoglyph confusable injection

## Rationale

Homoglyph attacks substitute visually-similar non-Latin characters into
otherwise Latin text — Cyrillic 'а' (U+0430) for Latin 'a' (U+0061), Greek 'ο'
(U+03BF) for Latin 'o' (U+006F), mathematical alphanumeric letters
(U+1D400-U+1D7FF) for ASCII letters — to bypass keyword matching while
remaining visually identical. The Trojan Source research (Boucher & Anderson,
2021) covers the broader class; UTS #39 (Unicode Security Mechanisms) defines
the canonical confusables data. The OWASP LLM Top 10 2025 LLM01 includes
homoglyph injection as a documented indirect-injection vector for skill
content.

The v1 trigger detects the *presence* of mixed-script words ≥5 chars (any
non-Latin character from the Cyrillic / Greek / Math-Alphanumeric blocks
adjacent to or interspersed with Latin letters within a single word). This is
a coarse detector — it will over-fire on legitimate mixed-script content.
The shadow window quantifies the cost; the v2 plan is to integrate the
Unicode confusables table (UTS #39) so the trigger fires only on
substitutions that visually match a Latin original. v2 also extends to
detect single-character substitutions in security-sensitive words ("admin",
"root", "sudo", "install").

Medium severity: the technique works but defeats only keyword-based
defenses, not semantic ones. Active mitigation is straightforward (NFKC
normalization at consumption time), so the impact is mostly on text-matching
review workflows rather than on LLM behavior directly.

## False positive history

(date-stamped log; updated by FP-audit harness and vendor-appeal outcomes)

## Version history

- v1 (Phase A 2026-W2): initial rule. Lands shadow; FP-audit gates promotion.
