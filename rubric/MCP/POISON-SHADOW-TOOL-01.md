---
ruleId: SS-MCP-POISON-SHADOW-TOOL-01
severity: critical
subScore: security
weight: 35
status: active
shadowUntil: null
appliesTo: [mcp]
frameworks: ["owasp-llm:llm01", "mitre-atlas:AML.T0051"]
title: >-
  Hidden-looking MCP tool name signals a shadow tool
categoryLabel: >-
  Tool poisoning
explanation: >-
  This server publishes a tool whose name (<code>{match}</code>) uses an "internal/private" naming
  convention. The agent still sees and may invoke it, but a human reviewing the manifest skips
  over names that visually signal "not for me" — letting a hidden tool act unreviewed.
severityRationale: >-
  A shadow tool can perform arbitrary tool actions while appearing benign in manifest review.
remediation:
  action: >-
    Rename internal-looking tools to plainly describe their purpose, or remove them if not consumer-facing.
  steps:
    - >-
      Confirm whether the flagged tool is meant to be reachable by the consuming agent.
    - >-
      If it is, give it a clear descriptive name; if it is not, remove it from the manifest.
trigger:
  type: regex_match
  pattern: '(?is)"name"\s*:\s*"[^"]*(?:_internal|__|\.hidden|_meta|_sys)[^"]*"'
  scope:
    paths: ['tools/manifest.json', '**/tools/manifest.json', 'manifest.json', '**/*.toolmanifest.json']
limitations:
  - "Heuristic-based: detects tool naming conventions suggestive of hidden / shadow tools. Cannot detect a shadow tool with a normal-looking name that becomes hidden via runtime registration order."
  - "Cannot detect shadow tools registered exclusively at runtime (no entry in the static manifest)."
priorArt:
  - https://invariantlabs.ai/blog/mcp-security-notification-tool-poisoning-attacks
  - https://arxiv.org/abs/2503.23278
---

# SS-MCP-POISON-SHADOW-TOOL-01 — Shadow / hidden MCP tool

## Rationale

A "shadow tool" is an MCP tool whose name or registration pattern suggests
intentional obfuscation from consumer review — names beginning with
underscores, names containing `_internal` or `__` (double-underscore Python
convention for private), or names suggestive of system tooling. Invariant
Labs' 2024 tool-poisoning research documents the pattern: a server publishes
a public-facing tool set plus one or more shadow tools that the consuming
agent will see (and may invoke) but that the human reviewer of the manifest
overlooks because the names visually signal "internal, not for me".

The rule detects on naming conventions; it cannot catch a shadow tool with
a normal-looking name. The conservative pattern set (underscores, dot-
hidden, _sys/_meta) is empirically derived from the Invariant Labs corpus
and the documented MCP attack-surface paper. Critical severity reflects the
attack class: a shadow tool can perform arbitrary tool actions while
appearing benign in the manifest review.

Active at landing. The vendor-appeal path covers the (rare) legitimate use
of underscore-prefixed tool names for actually-internal tools — those
appeals will inform v2 refinement of the pattern set.

## False positive history

(date-stamped log; updated by FP-audit harness and vendor-appeal outcomes)

## Version history

- v1 (Phase A 2026-W2): initial rule. Active at landing.
