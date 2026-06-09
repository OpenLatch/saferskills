---
ruleId: SS-HOOKS-SUPPLY-CHAIN-OWNER-XFER-01
severity: high
subScore: supply_chain
weight: 25
status: active
shadowUntil: null
appliesTo: [hooks]
frameworks: ["owasp-llm:llm03", "mitre-atlas:AML.T0010"]
title: >-
  Hook repo is maintained by a very small group
categoryLabel: >-
  Supply chain
explanation: >-
  This hook's repo has {count} or fewer contributors. A small maintainer pool is the
  classic takeover target — compromising one account, or persuading them to transfer
  ownership, lets an attacker push a malicious update that every consumer runs automatically.
severityRationale: >-
  a small maintainer pool is an easy takeover target for an artifact that runs with your privileges.
remediation:
  action: >-
    Confirm the maintainers and pin the hook to a reviewed, fixed revision before relying on it.
  steps:
    - >-
      Verify who controls the repo and whether ownership has recently changed hands.
    - >-
      Pin to a specific commit you have reviewed rather than tracking the latest version.
trigger:
  type: commit_history_check
  signal: contributor_count
  operator: lte
  threshold: 5
limitations:
  - "v1 detects only the structural signal — small contributor pool combined with the absence of an ownership-transfer announcement. The actual cross-time owner-transfer detection (GitHub ownership change events) lands in Phase B."
  - "Cannot detect repo transfers between organizations that the maintainer announces clearly — the rule fires on the structural state."
  - "Hook artifacts with longer ownership history naturally pass; the rule's threshold is intentionally conservative for the hook category specifically."
priorArt:
  - https://socket.dev/blog/the-pivotal-role-of-supply-chain-attacks-in-2024
  - https://chainguard.dev/unchained/the-anatomy-of-an-npm-takeover
---

# SS-HOOKS-SUPPLY-CHAIN-OWNER-XFER-01 — Hook repo small-pool ownership

## Rationale

The "package takeover" attack class (Chainguard's 2024 npm-takeover
analysis, Socket's supply-chain retrospective) succeeds against
small-contributor repos: an attacker either compromises the single
maintainer or convinces them to transfer ownership, then pushes a
malicious update that every existing consumer pulls. Hook artifacts are
particularly vulnerable because they run with user privileges and
execute automatically.

The v1 trigger is a structural-state check: hook repos with ≤5
contributors. Combined with the Phase B owner-transfer detection (which
queries GitHub for recent ownership-change events), the rule will fire
on the dangerous combination. The Phase A landing registers the
structural signal; Phase B refines the trigger.

High severity is appropriate for the supply_chain class on hook-scope
artifacts. Active at landing despite Phase B refinement because the
structural signal alone is meaningful for hooks specifically — they have
a different risk profile from MCP servers, which the threshold reflects.

## False positive history

(date-stamped log; updated by FP-audit harness and vendor-appeal outcomes)

## Version history

- v1 (Phase A 2026-W2): initial rule. Active at landing; v2 wires Phase B owner-transfer detection.
