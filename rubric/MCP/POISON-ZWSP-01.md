---
ruleId: SS-MCP-POISON-ZWSP-01
severity: high
subScore: security
weight: 25
status: active
shadowUntil: null
appliesTo: [mcp]
frameworks: ["owasp-llm:llm01", "mitre-atlas:AML.T0051"]
title: >-
  Zero-width characters hidden in an MCP tool manifest
categoryLabel: >-
  Obfuscation
explanation: >-
  An MCP tool's description is read by the agent as trusted instructions.
  This manifest packs three or more invisible zero-width characters (<code>{match}</code>) that the agent
  tokenizes but a human reviewer cannot see — a way to smuggle hidden instructions past review.
severityRationale: >-
  Clustered zero-width characters in a trusted manifest signal deliberate hiding of tokenized content.
remediation:
  action: >-
    Remove the zero-width characters (U+200B–U+200D, U+2060, U+FEFF) from the manifest.
  steps:
    - >-
      Open the flagged manifest and delete every zero-width / word-joiner / BOM codepoint.
    - >-
      Confirm no invisible characters remain in any tool <code>description</code>.
trigger:
  type: regex_match
  pattern: '[\u{200B}-\u{200D}\u{2060}\u{FEFF}]'
  flags: u
  scope:
    paths: ['tools/manifest.json', '**/tools/manifest.json', 'manifest.json', '**/*.toolmanifest.json']
  requiresCount: 3
limitations:
  - "Requires ≥3 zero-width characters to fire (FP reduction)."
  - "Cannot detect zero-width characters re-encoded as numeric entities."
  - "Cannot detect zero-width characters in dynamically-constructed tool descriptions."
priorArt:
  - https://invariantlabs.ai/blog/mcp-security-notification-tool-poisoning-attacks
  - https://embracethered.com/blog/posts/2023/llm-tricks-zero-width-characters/
---

# SS-MCP-POISON-ZWSP-01 — Zero-width character poisoning in MCP manifest

## Rationale

Zero-width characters in MCP tool manifests are the lower-impact cousin of
tag-channel poisoning — fewer invisibly-tokenized instructions per
character but a wider FP risk profile (copy-paste artifacts from chat tools
can introduce incidental zero-width spaces). The MCP-specific scope and
≥3-character threshold suppress the common FP modes while still catching
the deliberate-injection pattern.

High severity (not critical) reflects the lower-but-real impact relative to
tag-channel poisoning. Active at landing under the same scoping-and-threshold
justification as the SKILL sibling rule.

## False positive history

(date-stamped log; updated by FP-audit harness and vendor-appeal outcomes)

## Version history

- v1 (2026-01-09): initial rule. Active at landing.
