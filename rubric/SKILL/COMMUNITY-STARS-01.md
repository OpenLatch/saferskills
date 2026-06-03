---
ruleId: SS-SKILL-COMMUNITY-STARS-01
severity: info
subScore: community
weight: 0
status: active
shadowUntil: null
appliesTo: [skill, mcp, rules, hooks, plugin]
title: >-
  Fewer than 10 stars on the GitHub repository
categoryLabel: >-
  Community
explanation: >-
  The repository has under 10 GitHub stars. This is shown as community context only — stars are an
  easily-manipulated, low-quality proxy for adoption, so this signal carries weight 0 and does not
  affect the score.
remediation:
  action: >-
    No action required — context only.
trigger:
  type: metadata_check
  field: stars
  operator: lt
  value: 10
limitations:
  - "Star count is a noisy signal: stars can be bought, manipulated, or simply absent on new-but-legitimate projects."
  - "Info severity, weight 0: this rule does NOT affect the score. It surfaces in the trace only as community-context."
  - "Cannot detect star-velocity (sudden spike) which would be a more valuable signal. v2 candidate."
priorArt:
  - https://github.com/ossf/scorecard/blob/main/docs/checks.md#packaging
  - https://www.gharchive.org/
---

# SS-SKILL-COMMUNITY-STARS-01 — <10 stars on the GitHub repository

## Rationale

Star count is a low-quality community signal — easily manipulated, often
absent on legitimate niche tools, and a poor proxy for actual user base. We
include it as an `info`-severity rule with weight 0: it surfaces in the
public scan trace as community context but does not affect the aggregate
score. The intent is to give consumers an at-a-glance signal of community
adoption without giving the signal scoring power it doesn't deserve.

The 10-star threshold is the OpenSSF Scorecard "Packaging" default for the
"unpopular" signal. Repos below this threshold may be excellent and well-
maintained; the signal is informational only.

This rule is deliberately conservative: weight 0 means a low star count never
moves a score downward. The trade-off is that a vendor who manipulates star
count (bought stars) cannot use the trace to claim a misleading high score,
because stars don't affect score in the first place.

## False positive history

(date-stamped log; updated by FP-audit harness and vendor-appeal outcomes)

## Version history

- v1 (Phase A 2026-W2): initial rule. Active at landing as `info` (weight 0).
