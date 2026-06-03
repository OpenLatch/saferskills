---
ruleId: SS-SKILL-INJECT-UNICODE-TAG-01
severity: critical
subScore: security
weight: 35
status: active
shadowUntil: null
appliesTo: [skill, mcp, rules, hooks, plugin]
title: >-
  Invisible Unicode "tag" characters hidden in the instructions
categoryLabel: >-
  Obfuscation
explanation: >-
  Plane-14 tag characters (U+E0000–U+E007F) render as absolutely nothing to a person
  reading the file in any editor, yet every LLM tokenizer turns them into real tokens.
  An attacker can hide a whole second instruction in them — telling the agent to drop
  its safety rules or exfiltrate data — that no reviewer ever sees in the source.
severityRationale: >-
  there is no legitimate use for these codepoints, and they can carry a fully invisible system-prompt override.
remediation:
  action: >-
    Strip every plane-14 tag character and retype the affected text in plain ASCII.
  steps:
    - >-
      Run a strip-and-diff: remove all U+E0000–U+E007F characters and compare the result to the original.
    - >-
      If the visible text is unchanged after stripping, the removed characters were carrying a hidden payload — keep the stripped version.
trigger:
  type: regex_match
  pattern: '[\u{E0000}-\u{E007F}]'
  flags: u
  scope:
    paths: ['**/*.md', '**/*.yaml', '**/*.yml', '**/*.json', '**/SKILL.md']
limitations:
  - "Cannot detect tag-channel characters re-encoded as numeric entities (`&#xE0001;`); rule operates on decoded text only."
  - "Cannot detect tag-channel chars hidden inside compressed payloads (gzip / brotli); only post-decompression bytes are scanned."
  - "Does not distinguish documented use of plane-14 characters (rare) from injection — fires on any presence."
priorArt:
  - https://aws.amazon.com/blogs/security/defending-llm-applications-against-unicode-character-smuggling/
  - https://genai.owasp.org/llmrisk/llm01-prompt-injection/
  - https://embracethered.com/blog/posts/2024/hiding-and-finding-text-with-unicode-tags/
---

# SS-SKILL-INJECT-UNICODE-TAG-01 — Unicode tag-channel prompt injection

## Rationale

Unicode plane-14 "tag" characters (U+E0000 through U+E007F) are invisible to humans
in any current Unicode-aware renderer but are emitted as tokens by every production
LLM tokenizer. The 2024 publication of working invisible-instruction PoCs against
Bing Chat, Anthropic Claude, and OpenAI ChatGPT (Embrace the Red, "Hiding and
Finding Text with Unicode Tags", 2024) demonstrated that an LLM consuming a
markdown skill body would honor instructions embedded as tag-channel codepoints
even though a human reviewing the same file in any editor sees nothing. AWS
published the canonical defense doctrine in 2025 ("Defending LLM applications
against Unicode character smuggling") recommending strip-and-diff verification on
all LLM input, and the OWASP LLM Top 10 2025 LLM01 (Prompt Injection) classifies
this as a primary indirect-injection vector for agent platforms.

A `critical` severity is justified on two grounds. First, detection is near-zero-FP:
there is no legitimate authoring use case for plane-14 codepoints in a skill body,
MCP tool description, hook command, or rule file — every observed instance in the
wild has been adversarial. Second, the impact is full system-prompt override: the
attacker can instruct the consuming agent to ignore its safety constraints, exfil
credentials, or modify subsequent tool invocations without the maintainer or
reviewer ever seeing the instruction in the source. The rule fires on any single
codepoint match across the file globs in scope — a stricter `requiresCount` would
weaken the contract for no measurable FP reduction.

The trigger applies across all five artifact kinds because the underlying
substrate (text that an LLM agent will consume) is identical in each. No
documented legitimate use case exists for plane-14 in any of the in-scope formats;
a skill author who needs i18n marker characters should use BCP 47 language tags or
a documented namespace, not the tag-channel range.

## False positive history

(date-stamped log; updated by FP-audit harness and vendor-appeal outcomes)

## Version history

- v1 (Phase A 2026-W2): initial rule. Active at landing per FP-audit prior to merge.
