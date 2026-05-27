---
ruleId: SS-SKILL-INJECT-FENCED-RUN-01
severity: high
subScore: security
weight: 25
status: shadow
shadowUntil: 2026-W3-end
appliesTo: [skill, mcp, rules, hooks, plugin]
trigger:
  type: regex_match
  pattern: '(?ms)^```(?:bash|sh|zsh|powershell|pwsh|cmd|python|node|js|ts)\s*$\s+(?:.*?\b(?:please|now|then|next|first)\s+(?:run|execute|invoke|call|trigger)\b.*?|.*?(?:run|execute|invoke|call|trigger)\s+(?:this|the\s+(?:above|below|following))\s+(?:command|code|script)\b.*?)```'
  scope:
    paths: ['**/*.md', '**/SKILL.md']
limitations:
  - "Cannot detect imperative instructions that don't use the curated verb set (run/execute/invoke/call/trigger)."
  - "Cannot detect fenced-imperative when the natural-language wrapper is outside the fence (most skills place instructions BEFORE a fence, not inside it)."
  - "May over-fire on tutorials demonstrating the safe execution of example code; shadow window measures real-world impact."
priorArt:
  - https://arxiv.org/abs/2510.26328
  - https://genai.owasp.org/llmrisk/llm01-prompt-injection/
  - https://invariantlabs.ai/blog/mcp-security-notification-tool-poisoning-attacks
---

# SS-SKILL-INJECT-FENCED-RUN-01 — Fenced-imperative run pattern

## Rationale

Recent research (arXiv 2510.26328, 2025) documented the "fenced-imperative"
prompt-injection pattern: an adversarial skill embeds shell or script code
inside a Markdown fence accompanied by natural-language imperatives directing
the consuming LLM agent to execute the fenced content as part of normal
skill-following behaviour. Unlike classic injection ("ignore previous
instructions"), the pattern looks like legitimate documentation to a casual
reader and uses the LLM's tendency to follow nearby imperatives as the attack
vector. Invariant Labs' MCP tool-poisoning analysis (2024) documented an
analogous pattern in MCP tool descriptions: structured-looking content with
embedded run-this imperatives.

The shadow landing reflects the inherent FP risk: skill tutorials legitimately
demonstrate fenced code that users (or agents on user instruction) should
execute. The trigger is narrowed to imperative-verb + this-code patterns to
suppress most legitimate cases, but the 7-day shadow window will quantify the
residual FP rate. If FP rate exceeds 10% on the 100-item fixture, the rule
remains shadow with a maintainer-led narrowing of the verb set or the
requirement that the imperative appear within the fence (not before or after).

`high` severity is justified by the outcome class: a successful fenced-
imperative injection causes the consuming agent to execute attacker-supplied
shell — same impact class as the SS-HOOKS-RCE-* rule family. The rule complements,
rather than duplicates, the hooks-class rules: it catches the same attack
class one upstream layer (a hostile skill that would later be invoked from a
trusted hook).

## False positive history

(date-stamped log; updated by FP-audit harness and vendor-appeal outcomes)

## Version history

- v1 (Phase A 2026-W2): initial rule. Lands shadow; FP-audit gates promotion.
