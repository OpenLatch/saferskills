---
ruleId: SS-SKILL-COMMUNITY-CONTRIBUTORS-01
severity: info
subScore: community
weight: 0
status: shadow
shadowUntil: 2026-W3-end
appliesTo: [skill, mcp, rules, hooks, plugin]
trigger:
  type: commit_history_check
  signal: contributor_count
  operator: eq
  threshold: 1
limitations:
  - "Single-author projects are common and often legitimate (research code, hobby tools, focused micro-libraries). Info severity reflects this."
  - "Bot accounts (dependabot, renovate) inflate the contributor count without indicating real community. v2 will exclude bot accounts."
  - "Cannot distinguish a solo project from one with many shadow-contributors via squash-merge from a fork."
priorArt:
  - https://github.com/ossf/scorecard/blob/main/docs/checks.md#contributors
  - https://chaoss.community/kb/metric-contributors/
---

# SS-SKILL-COMMUNITY-CONTRIBUTORS-01 — Single-author repository

## Rationale

A single-contributor repository is a community-context signal: any failure of
the single maintainer (illness, abandonment, compromise) immediately affects
every downstream consumer. OpenSSF Scorecard's "Contributors" check codifies
this concern.

`info` severity at weight 0 is the correct positioning: solo projects are
common and legitimate, and we do not want to penalise small, focused tools.
The signal surfaces in the scan trace as community-context — a consumer
considering deep integration with a single-author project can see this and
weigh it.

The rule lands shadow despite the zero weight because the v2 refinement (excluding
bot accounts) will benefit from real-world FP data on the v1 trigger. The
weight stays 0 across the shadow→active promotion.

## False positive history

(date-stamped log; updated by FP-audit harness and vendor-appeal outcomes)

## Version history

- v1 (Phase A 2026-W2): initial rule. Lands shadow as `info` (weight 0).
