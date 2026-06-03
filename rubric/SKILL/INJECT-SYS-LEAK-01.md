---
ruleId: SS-SKILL-INJECT-SYS-LEAK-01
severity: medium
subScore: security
weight: 15
status: shadow
shadowUntil: 2026-W3-end
appliesTo: [skill, mcp, rules, hooks, plugin]
title: >-
  Request for the agent to reveal its system prompt
categoryLabel: >-
  Prompt injection
explanation: >-
  The text <code>{match}</code> asks the agent to disclose its hidden system prompt or
  initial instructions. That is often the first step of a larger attack: knowing the
  system prompt lets an attacker craft inputs that defeat its constraints by mimicking
  its own voice.
severityRationale: >-
  it scores the disclosure intent; whether extraction succeeds depends on the host model's own mitigations.
remediation:
  action: >-
    Remove the solicitation asking the agent to reveal its system prompt or hidden instructions.
  steps:
    - >-
      Delete the <code>repeat/reveal/print your system prompt</code> request from the skill.
    - >-
      If you are debugging your own prompt, do so in a private dev harness rather than baking the request into a shipped skill.
trigger:
  type: regex_match
  pattern: '(?i)\b(repeat|reveal|output|print|show|tell\s+me)\s+(your|the)\s+(system\s+prompt|initial\s+instructions?|original\s+prompts?|hidden\s+instructions?|prompt\s+template)\b'
  scope:
    paths: ['**/*.md', '**/*.yaml', '**/*.yml', '**/*.json', '**/SKILL.md']
limitations:
  - "FP risk on skills designed to introspect or debug model behaviour (prompt-engineering tutorials, evaluation toolkits)."
  - "Cannot detect indirect leak attempts that don't use the canonical 'system prompt' vocabulary."
  - "Does not currently chain with model-level mitigations (modern models partially refuse this class of request); SaferSkills flags the intent regardless of model response."
priorArt:
  - https://arxiv.org/abs/2307.06865
  - https://genai.owasp.org/llmrisk/llm07-system-prompt-leakage/
---

# SS-SKILL-INJECT-SYS-LEAK-01 — System-prompt leakage solicitation

## Rationale

System-prompt leakage (OWASP LLM Top 10 2025 LLM07) is the class of injection
that asks the model to reveal its hidden system instructions, often as a
precursor to a more sophisticated prompt-injection attack: knowing the system
prompt lets the attacker craft inputs that defeat its constraints by impersonating
its voice. The Zhang et al. (2023; arXiv 2307.06865) corpus catalogued this
pattern across 40+ phrasing variants; the OWASP entry codifies it as a primary
disclosure vector for any deployed LLM application that builds its system
prompt from sensitive context (API keys, retrieval data, internal procedures).

The medium severity reflects an intermediate impact: the rule catches the
intent, but extraction success depends on the consuming model's specific
mitigations. We score the intent, not the outcome — a skill that asks for the
system prompt is engaging in an adversarial pattern regardless of whether the
host model refuses. The shadow window collects FP data from legitimate
prompt-debugging skills before promotion; the trigger is intentionally narrow
(specific noun phrases tied to specific imperative verbs) to bound the FP
surface.

## False positive history

(date-stamped log; updated by FP-audit harness and vendor-appeal outcomes)

## Version history

- v1 (Phase A 2026-W2): initial rule. Lands shadow; FP-audit gates promotion.
