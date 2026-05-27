---
ruleId: SS-SKILL-INJECT-IGNORE-01
severity: high
subScore: security
weight: 25
status: shadow
shadowUntil: 2026-W3-end
appliesTo: [skill, mcp, rules, hooks, plugin]
trigger:
  type: regex_match
  pattern: '(?i)\b(ignore|disregard|forget|override)\s+(all\s+)?(previous|prior|above|earlier)\s+(instructions?|prompts?|rules?|system\s+prompts?)\b'
  scope:
    paths: ['**/*.md', '**/*.yaml', '**/*.yml', '**/*.json', '**/SKILL.md']
limitations:
  - "False-positives on roleplay skills, jailbreak research documentation, prompt-engineering tutorials, and any meta-discussion of LLM safety. Shadow window measures real-world FP rate."
  - "Cannot detect non-English equivalents of the imperative pattern. Coverage at W2 is English-only; multilingual extension is a Phase 2 RFC."
  - "Cannot detect the pattern when split across formatting or hidden in comments."
priorArt:
  - https://genai.owasp.org/llmrisk/llm01-prompt-injection/
  - https://arxiv.org/abs/2306.05499
  - https://www.lakera.ai/blog/jailbreaking-large-language-models-guide
---

# SS-SKILL-INJECT-IGNORE-01 — "Ignore previous instructions" pattern

## Rationale

The "ignore previous instructions" imperative is the prototypical direct-
injection phrasing studied since the earliest LLM-jailbreak research (Perez &
Ribeiro, 2022; OWASP LLM Top 10 2025 LLM01 §Direct injection). Detecting the
exact phrasing has near-zero true-positive cost when the artifact is a hostile
skill body, but suffers a meaningful false-positive rate: prompt-engineering
tutorials, jailbreak research notes, safety-evaluation skills, and roleplay
skills (where the user-character is supposed to ignore the model's defaults)
all legitimately contain the pattern. We therefore land the rule in
`status: shadow` for the standard 7-day FP-audit window; only after the harness
confirms a <10% FP rate against the 100-item fixture suite does the rule
promote to `active`.

`high` severity is set in anticipation of promotion: when the rule does fire
on adversarial content, the impact matches Unicode-smuggling rules (full
system-prompt override). The shadow weight of 0 ensures no false positive
bites the vendor during the audit window; the audit log of fires + outcomes
becomes the public artifact justifying the eventual promotion decision.

The trigger is intentionally narrow (anchored at word boundaries, restricted
to a small verb set, requires an explicit "previous/prior/above" qualifier).
Broader patterns ("override system", "act as if you have no rules", etc.) live
in separate rules (SS-SKILL-INJECT-ROLE-01, SS-SKILL-INJECT-DONT-ASK-01) so
that promotion decisions can be made per-pattern rather than batch-locked.

## False positive history

(date-stamped log; updated by FP-audit harness and vendor-appeal outcomes)

## Version history

- v1 (Phase A 2026-W2): initial rule. Lands shadow; FP-audit gates promotion.
