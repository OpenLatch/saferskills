---
ruleId: SS-MCP-POISON-BIDI-01
severity: critical
subScore: security
weight: 35
status: active
shadowUntil: null
appliesTo: [mcp]
frameworks: ["owasp-llm:llm01", "mitre-atlas:AML.T0051"]
title: >-
  BiDi-override characters reorder text in an MCP tool description
categoryLabel: >-
  Prompt injection
explanation: >-
  An MCP tool's <code>description</code> is read by the agent as trusted instructions.
  This one embeds bidirectional-override characters (<code>{match}</code>) so the manifest renders one
  thing to a human reviewer but tokenizes a different, reordered instruction to the agent.
severityRationale: >-
  Reordered hidden text in a trusted tool description can steer the consuming agent against the reviewer's intent.
remediation:
  action: >-
    Remove the BiDi-override control characters (U+202A–U+202E, U+2066–U+2069) from the tool description.
  steps:
    - >-
      Open the flagged tool's <code>description</code> and delete every BiDi-override codepoint.
    - >-
      Verify the rendered text matches the byte order — no hidden reordering remains.
trigger:
  type: regex_match
  pattern: '[\u{202A}-\u{202E}\u{2066}-\u{2069}]'
  flags: u
  scope:
    paths: ['tools/manifest.json', '**/tools/manifest.json', 'manifest.json', '**/server.py', '**/server.ts', '**/server.js', '**/*.toolmanifest.json']
limitations:
  - "Cannot detect BiDi attacks via inherent-RTL scripts (Arabic / Hebrew text used in MCP tools for non-English users)."
  - "Cannot distinguish legitimate i18n use of BiDi overrides from injection."
priorArt:
  - https://invariantlabs.ai/blog/mcp-security-notification-tool-poisoning-attacks
  - https://www.trojansource.codes/
  - https://nvd.nist.gov/vuln/detail/CVE-2021-42574
---

# SS-MCP-POISON-BIDI-01 — BiDi-override poisoning in MCP manifest

## Rationale

MCP-specific instance of the Trojan Source / BiDi-override attack class
(parallel SKILL rule SS-SKILL-INJECT-BIDI-01). An MCP server with a
BiDi-override in its tool description renders one thing to a human reviewing
the manifest and tokenizes another to the consuming LLM. The Invariant Labs
2024 tool-poisoning research catalogued this as one of the documented
MCP-specific attack patterns.

Critical severity matches the SKILL sibling. Active at landing — the
manifest-and-server-source scoping bounds the FP surface, and legitimate
i18n use of explicit BiDi-overrides in MCP tool definitions is functionally
nil (the few real-world cases use script-aware rendering without explicit
overrides).

## False positive history

(date-stamped log; updated by FP-audit harness and vendor-appeal outcomes)

## Version history

- v1 (2026-01-09): initial rule. Active at landing.
