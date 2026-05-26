---
ruleId: SS-MCP-POISON-DESCRIPTION-CREEP-01
severity: critical
subScore: security
weight: 35
status: active
shadowUntil: null
appliesTo: [mcp]
trigger:
  type: regex_match
  pattern: '(?is)"description"\s*:\s*"[^"]{2000,}"'
  scope:
    paths: ['tools/manifest.json', '**/tools/manifest.json', 'manifest.json', '**/*.toolmanifest.json']
limitations:
  - "Length-based heuristic — does not analyze the description content. A legitimate complex tool may have a long description; vendor-appeal data will tune the threshold."
  - "Cannot detect description-creep injected via dynamic construction (server-side string concatenation)."
  - "Cannot detect multi-line JSON-formatted descriptions where the length is hidden by line wrapping in the source view."
priorArt:
  - https://invariantlabs.ai/blog/mcp-security-notification-tool-poisoning-attacks
  - https://arxiv.org/abs/2503.23278
---

# SS-MCP-POISON-DESCRIPTION-CREEP-01 — Oversized MCP tool description

## Rationale

Invariant Labs' 2024 tool-poisoning research and the 2025 arXiv 2503.23278
paper on MCP attack surfaces both document the same pattern: a hostile MCP
server publishes a tool with an extremely long `description` field —
2000+ characters — into which the attacker hides instructions, reasoning
chains, or full system-prompt overrides. The consuming LLM reads the
description as part of normal tool-discovery, but a human reviewer of the
manifest often skims it given the length, missing the embedded payload.

The 2000-character threshold is conservative: typical legitimate MCP tool
descriptions are 100-500 characters (matching natural-language explanations
of what a single tool does). Length above 2000 characters in a tool
description is exceptional and warrants review. Critical severity is
appropriate because the documented use of this pattern in the wild has
universally been adversarial.

Active at landing. The vendor-appeal path documents legitimate exceptions
(complex tools with rich operational guidance) on a per-tool basis.

## False positive history

(date-stamped log; updated by FP-audit harness and vendor-appeal outcomes)

## Version history

- v1 (Phase A 2026-W2): initial rule. Active at landing with 2000-char threshold.
