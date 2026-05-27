---
ruleId: SS-MCP-POISON-ZWSP-01
severity: high
subScore: security
weight: 25
status: active
shadowUntil: null
appliesTo: [mcp]
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

- v1 (Phase A 2026-W2): initial rule. Active at landing.
