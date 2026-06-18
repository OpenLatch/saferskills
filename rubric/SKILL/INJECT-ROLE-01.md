---
ruleId: SS-SKILL-INJECT-ROLE-01
severity: high
subScore: security
weight: 25
status: shadow
shadowUntil: 2026-01-18
appliesTo: [skill, mcp, rules, hooks, plugin]
frameworks: ["owasp-llm:llm01", "mitre-atlas:AML.T0051"]
title: >-
  Role-override jailbreak persona in the skill text
categoryLabel: >-
  Prompt injection
explanation: >-
  The phrase <code>{match}</code> matches a known role-override jailbreak — DAN, "developer
  mode", "jailbroken", "unrestricted", or an evil/malicious persona. Embedded in a skill,
  it tries to push the agent into an adversarial role that drops its safety constraints,
  without the person running the skill realizing it.
severityRationale: >-
  a successful role override converts a benign agent context into an unconstrained one.
remediation:
  action: >-
    Remove the persona-assignment phrase, or restate it as quoted research material, not an instruction.
  steps:
    - >-
      Delete the <code>you are / act as / pretend to be &lt;jailbreak persona&gt;</code> line.
    - >-
      For red-team or educational skills, keep such strings inside a clearly marked example block so they are read as data, not as a directive.
trigger:
  type: regex_match
  pattern: '(?i)\b(you\s+are|act\s+as|pretend\s+(to\s+be|you\s+are)|roleplay\s+as)\s+(DAN|developer\s+mode|jailbroken|unrestricted|uncensored|an?\s+(evil|malicious|harmful|amoral)\s+\w+)\b'
  scope:
    paths: ['**/*.md', '**/*.yaml', '**/*.yml', '**/*.json', '**/SKILL.md']
limitations:
  - "FP rate on jailbreak-research and red-team skills is expected to be non-trivial — shadow window measures real-world impact."
  - "Cannot detect novel role-override personas coined after the rule lands. The DAN/developer-mode/jailbroken seed list is curated; new personas require a v2 rule revision."
  - "Cannot detect role-override embedded in tool-call arguments dynamically constructed at runtime."
priorArt:
  - https://arxiv.org/abs/2306.05499
  - https://genai.owasp.org/llmrisk/llm01-prompt-injection/
  - https://www.jailbreakchat.com/
  - https://arxiv.org/abs/2310.06987
---

# SS-SKILL-INJECT-ROLE-01 — Role-override jailbreak pattern

## Rationale

Role-override jailbreaks (DAN — "Do Anything Now"; "developer mode"; "you are
an unrestricted AI") are the second-most-studied direct-injection class after
the "ignore previous instructions" pattern. The 2023 jailbreakchat corpus
documented ~100 stable variants; arXiv 2310.06987 (Zou et al., 2023) showed
that even after model-level RLHF mitigations, role-override prompts retain
non-trivial success rates against modern aligned models. When such a phrase
appears in a skill body, hook command, or MCP tool description, it converts an
otherwise benign agent context into an adversarial one without the consumer's
awareness.

The rule lands `shadow` because the FP surface is real: legitimate red-team
skills, safety-evaluation toolkits, and educational jailbreak documentation
contain the trigger pattern by design. The 7-day shadow window collects audit
data; if the FP rate exceeds 10% against the 100-item fixture suite, the rule
remains shadow with extended `shadowUntil` and a maintainer-led pattern
refinement (e.g. requiring an imperative verb adjacent to the role-name
phrase).

The pattern set is curated from public jailbreak research as of 2026-01-09: DAN,
developer mode, jailbroken, unrestricted, uncensored, and the modifier-noun
construction (evil/malicious/harmful/amoral + agent/AI). New personas coined
after the rule lands require a v2 revision via the RFC process; the curated
list is a deliberate engineering trade-off between coverage and FP control.

## False positive history

(date-stamped log; updated by FP-audit harness and vendor-appeal outcomes)

## Version history

- v1 (2026-01-09): initial rule. Lands shadow; FP-audit gates promotion.
