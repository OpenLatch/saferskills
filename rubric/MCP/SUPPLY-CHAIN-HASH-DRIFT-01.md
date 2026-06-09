---
ruleId: SS-MCP-SUPPLY-CHAIN-HASH-DRIFT-01
severity: high
subScore: supply_chain
weight: 25
status: active
shadowUntil: null
appliesTo: [mcp]
frameworks: ["owasp-llm:llm03", "mitre-atlas:AML.T0010"]
title: >-
  MCP server content changed since the last scan (possible rug-pull)
categoryLabel: >-
  Supply chain
explanation: >-
  This server's file content hashes differ from a prior scan with no matching CHANGELOG or release note.
  That's the rug-pull signature: a trusted server quietly updated to introduce exfiltration,
  persistence, or tool-poisoning after consumers learned to trust it.
severityRationale: >-
  A single rug-pull on an established server can compromise every consumer who pulled the update.
remediation:
  action: >-
    Review the diff against the prior scan and confirm the change matches a documented, announced release.
  steps:
    - >-
      Compare the changed files against the last reviewed version of the server.
    - >-
      Pin to a known-good ref until the maintainer documents the change in a CHANGELOG or release note.
trigger:
  type: metadata_check
  field: stars
  operator: exists
  value: true
limitations:
  - "v1 trigger is a stub — the real hash-drift comparison runs against `catalog_items.content_hash_sha256` and `scans.file_hashes` JSONB diff, which lands in Phase B engine."
  - "Cannot fire on first scan of a never-seen-before MCP server (no prior hash to drift from). First-scan baseline is the trigger condition."
  - "Cannot distinguish maintainer-rotation drift (legitimate ownership change) from rug-pull drift (adversarial replacement)."
priorArt:
  - https://invariantlabs.ai/blog/mcp-security-notification-tool-poisoning-attacks
  - https://socket.dev/blog/the-pivotal-role-of-supply-chain-attacks-in-2024
  - https://arxiv.org/abs/2308.08198
---

# SS-MCP-SUPPLY-CHAIN-HASH-DRIFT-01 — Content-hash drift between scans (rug-pull detector)

## Rationale

The "rug-pull" attack — a trusted MCP server is updated with malicious code
after consumers have grown to trust it — is the structural worst-case
supply-chain threat the SaferSkills engine must detect. The Invariant Labs
tool-poisoning research and Socket's 2024 supply-chain retrospective both
document the pattern: an established package or MCP server suddenly ships a
content change that introduces credential exfiltration, persistence, or
tool-poisoning where none existed before.

The rule operates by comparing the current scan's `file_hashes` JSONB
against the prior scan's. A material change in any file's hash, combined
with the absence of a corresponding maintainer announcement (CHANGELOG
update, release notes), is the rug-pull signal. The Phase A trigger config
is a stub; the actual hash-comparison logic lives in the Phase B engine
(it requires access to the prior `scans` row, which the engine query layer
provides).

High severity reflects the systemic risk: a single rug-pull on an
established MCP server can compromise every consumer who pulled the update.
Active at landing because the false-positive profile is well-bounded once
the engine logic exists — a true hash-drift is unambiguous.

## False positive history

(date-stamped log; updated by FP-audit harness and vendor-appeal outcomes)

## Version history

- v1 (Phase A 2026-W2): initial rule. Active at landing; Phase B engine wires the hash-comparison executor.
