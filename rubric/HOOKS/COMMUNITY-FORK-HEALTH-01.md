---
ruleId: SS-HOOKS-COMMUNITY-FORK-HEALTH-01
severity: info
subScore: community
weight: 0
status: shadow
shadowUntil: 2026-01-18
appliesTo: [hooks]
title: >-
  Hook has very few forks
categoryLabel: >-
  Community
explanation: >-
  This hook has fewer than {count} forks. Low fork counts can hint at limited community
  use or little third-party validation, but they are a noisy proxy — many sound hooks are
  rarely forked because they need no customization. This is context only and does not affect the score.
remediation:
  action: >-
    No action required — context only.
trigger:
  type: metadata_check
  field: fork_count
  operator: lt
  value: 3
limitations:
  - "Info severity, weight 0 — does not affect score; surfaces in trace only."
  - "Fork count is a noisy proxy for community use; many legitimate hooks have low fork counts because they don't need customization."
  - "Cannot distinguish recent forks (active community) from historical forks (stale)."
priorArt:
  - https://github.com/ossf/scorecard/blob/main/docs/checks.md#packaging
---

# SS-HOOKS-COMMUNITY-FORK-HEALTH-01 — Hook with <3 forks

## Rationale

A community-context signal — hook artifacts with very few forks may
indicate low community engagement, no third-party validation of the
behavior, or extreme novelty. The signal is noisy and lands at info
severity (weight 0) for the same reasons as the other Community-axis
rules: the operational value is reference context, not score impact.

Shadow window will determine whether this signal correlates meaningfully
with any operational quality measure. If not, it may be removed in v2.

## False positive history

(date-stamped log; updated by FP-audit harness and vendor-appeal outcomes)

## Version history

- v1 (2026-01-09): initial rule. Lands shadow as `info` (weight 0).
