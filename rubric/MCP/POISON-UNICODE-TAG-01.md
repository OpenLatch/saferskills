---
ruleId: SS-MCP-POISON-UNICODE-TAG-01
severity: critical
subScore: security
weight: 35
status: active
shadowUntil: null
appliesTo: [mcp]
trigger:
  type: regex_match
  pattern: '[\u{E0000}-\u{E007F}]'
  flags: u
  scope:
    paths: ['tools/manifest.json', '**/tools/manifest.json', 'manifest.json', '**/server.py', '**/server.ts', '**/server.js', '**/*.toolmanifest.json']
limitations:
  - "Cannot detect tag-channel characters re-encoded as numeric entities; rule operates on decoded text only."
  - "Cannot detect tag-channel chars embedded only in runtime-constructed tool descriptions (e.g. a tool whose description is f-stringed from user input)."
  - "Server-source detection is regex-based; obfuscation via string concatenation evades the rule."
priorArt:
  - https://invariantlabs.ai/blog/mcp-security-notification-tool-poisoning-attacks
  - https://aws.amazon.com/blogs/security/defending-llm-applications-against-unicode-character-smuggling/
  - https://genai.owasp.org/llmrisk/llm01-prompt-injection/
---

# SS-MCP-POISON-UNICODE-TAG-01 — Unicode tag-channel poisoning in MCP tool description

## Rationale

The MCP-specific instance of the Unicode tag-channel attack (cf. parallel
SKILL rule SS-SKILL-INJECT-UNICODE-TAG-01). MCP tool descriptions and
manifests are the canonical attack surface that Invariant Labs documented in
their 2024 tool-poisoning research: an attacker embeds invisible
plane-14 codepoints in a tool's `description` field, the host LLM tokenizes
them as instructions, and subsequent tool invocations follow the embedded
directives — all while a human reviewing the manifest sees the apparent
description unchanged.

The rule scopes specifically to MCP manifest filenames and server source code
(where the manifest is constructed). Critical severity matches the SKILL
sibling rule for the same reasons: detection is near-zero-FP (no legitimate
use case for plane-14 in tool descriptions); impact is full system-prompt
override of the consuming agent; the defensive cost to maintainers is zero.

Active at landing. The MCP-specific scope and the SKILL-parallel structure
mean this rule's FP profile is well-bounded — the same content patterns that
fire SS-SKILL-INJECT-UNICODE-TAG-01 fire here when they appear in MCP-specific
files.

## False positive history

(date-stamped log; updated by FP-audit harness and vendor-appeal outcomes)

## Version history

- v1 (Phase A 2026-W2): initial rule. Active at landing.
