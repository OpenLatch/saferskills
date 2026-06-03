---
ruleId: SS-SKILL-INJECT-DONT-ASK-01
severity: medium
subScore: security
weight: 15
status: shadow
shadowUntil: 2026-W3-end
appliesTo: [skill, mcp, rules, hooks, plugin]
title: >-
  Instruction telling the agent not to ask for approval
categoryLabel: >-
  Prompt injection
explanation: >-
  The text <code>{match}</code> tells the agent to skip the normal "ask the user first"
  gate. Used adversarially it removes the human-in-the-loop check before destructive or
  sensitive actions, turning a normally-gated agent into a fire-and-forget executor.
severityRationale: >-
  it fires on intent; the real damage depends on the host agent's own approval-gating.
remediation:
  action: >-
    Remove the approval-skipping instruction, or scope it narrowly to a specific safe, reversible action.
  steps:
    - >-
      Delete blanket "don't ask / no need to confirm" directives from the skill.
    - >-
      If the skill is a genuine autonomous job, restrict the opt-out to a named non-destructive action rather than all actions.
trigger:
  type: regex_match
  pattern: '(?i)\b(do\s+not|don[’'']t|never|no\s+need\s+to)\s+(ask|confirm|prompt|request\s+permission|wait\s+for\s+approval|seek\s+consent|verify\s+with\s+the\s+user)\b'
  scope:
    paths: ['**/*.md', '**/SKILL.md', '**/CLAUDE.md']
limitations:
  - "Legitimate use case: autonomous-mode skills (background tasks, scheduled jobs) explicitly opt out of approval prompts. Shadow window will quantify the FP rate on this legitimate cohort."
  - "Cannot distinguish skill-level autonomy declarations from injection-style mid-skill instructions; both fire on the same regex."
  - "Cannot detect equivalents in non-English text."
priorArt:
  - https://genai.owasp.org/llmrisk/llm06-excessive-agency/
  - https://docs.anthropic.com/en/docs/agents-and-tools/computer-use
---

# SS-SKILL-INJECT-DONT-ASK-01 — "Don't ask the user" autonomy override

## Rationale

A subtle injection pattern: instruct the consuming agent to skip the normal
user-approval gates around destructive or sensitive actions. The OWASP LLM Top
10 2025 LLM06 (Excessive Agency) explicitly calls out the class of injection
that strips human-in-the-loop gates; a hostile skill saying "never prompt the
user before running this" can convert a normally-gated agent into a fire-and-
forget executor of arbitrary actions.

The FP surface is real and intentional: legitimate autonomous-mode skills
(scheduled background tasks, batch jobs, CI runs) explicitly opt out of user
prompts, and the skill author phrases the opt-out exactly the same way as an
injection author would. The shadow window will collect FP data; the
likely promotion path is to narrow the trigger to require the imperative
pattern alongside a sensitive-action verb (run, install, deploy, delete, etc.)
within the same paragraph.

Medium severity reflects the impact uncertainty: the rule fires on intent;
whether the consuming agent honours the imperative depends on its own
safety-gating implementation. The FP audit data and operational outcomes will
inform whether to promote at medium, lift to high, or demote to info.

## False positive history

(date-stamped log; updated by FP-audit harness and vendor-appeal outcomes)

## Version history

- v1 (Phase A 2026-W2): initial rule. Lands shadow; FP-audit gates promotion.
