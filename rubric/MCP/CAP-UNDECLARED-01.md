---
ruleId: SS-MCP-CAP-UNDECLARED-01
severity: high
subScore: security
weight: 25
status: shadow
shadowUntil: 2026-W3-end
appliesTo: [mcp]
frameworks: ["owasp-llm:llm06", "mitre-atlas:AML.T0053"]
title: >-
  MCP server spawns subprocesses without declaring the capability
categoryLabel: >-
  Undeclared capability
explanation: >-
  The server's source spawns processes (e.g. <code>subprocess</code>, <code>child_process</code>, <code>exec()</code>)
  but its manifest never declares that capability, so the consuming client can't warn the user
  that this server may run shell commands on their machine.
severityRationale: >-
  Undeclared shell-exec is the prototypical MCP sandbox-escape vector documented in the research.
remediation:
  action: >-
    Declare the process-spawning behavior in the manifest's capabilities, or remove the unnecessary exec call.
  steps:
    - >-
      Confirm whether the subprocess/exec call is needed for a consumer-facing tool.
    - >-
      If it is, declare the capability so clients can surface it; if not, remove the call.
trigger:
  type: composite_and_or
  op: and
  children:
    - type: regex_match
      pattern: '(?is)\b(subprocess|os\.system|spawn|execve|child_process|exec\s*\()'
      scope:
        paths: ['**/server.py', '**/server.ts', '**/server.js', '**/index.py', '**/index.ts', '**/index.js']
    - type: regex_match
      pattern: '(?is)"capabilities"\s*:\s*\{[^}]*"tools"\s*:\s*\{[^}]*"listChanged"\s*:\s*true[^}]*\}[^}]*\}'
      scope:
        paths: ['tools/manifest.json', 'manifest.json']
limitations:
  - "Heuristic detection of process-spawning primitives — cannot detect dynamically-loaded process libraries (e.g. importlib-resolved subprocess wrappers)."
  - "Manifest capability declarations are advisory; the MCP protocol does not enforce them. The rule flags discrepancy as a transparency signal, not a hard guarantee."
  - "FP risk on MCP servers that subprocess only for legitimate internal lifecycle (worker management, not user-facing tool execution). Shadow window measures."
priorArt:
  - https://modelcontextprotocol.io/specification/server/tools
  - https://invariantlabs.ai/blog/mcp-security-notification-tool-poisoning-attacks
---

# SS-MCP-CAP-UNDECLARED-01 — MCP server spawns subprocesses without capability declaration

## Rationale

The MCP protocol's `capabilities` declaration allows servers to advertise
what kinds of operations they perform. A server that spawns subprocesses
(shell commands, child processes, etc.) without declaring this in its
capabilities creates a transparency mismatch: the consuming client cannot
inform the user "this server may execute shell commands" because the server
has not declared the capability.

The detection composites two signals: (1) presence of subprocess/exec
primitives in server source code, and (2) absence of the relevant capability
declaration in the published manifest. Both must be true for the rule to
fire. This bounds FP risk — a server that legitimately exec()s internally
for lifecycle management without exposing the capability to clients does
not match the "spawn primitive in source" pattern alone.

The shadow window will quantify FP on borderline cases. High severity is
warranted: the un-declared shell-exec capability is the prototypical MCP
sandbox-escape vector documented in the Invariant Labs and arXiv research.

## False positive history

(date-stamped log; updated by FP-audit harness and vendor-appeal outcomes)

## Version history

- v1 (Phase A 2026-W2): initial rule. Lands shadow; FP-audit gates promotion.
