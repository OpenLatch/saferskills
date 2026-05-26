---
ruleId: SS-RULES-COMMUNITY-INSTALLS-01
severity: info
subScore: community
weight: 0
status: active
shadowUntil: null
appliesTo: [rules]
trigger:
  type: metadata_check
  field: stars
  operator: lt
  value: 5
limitations:
  - "Info severity, weight 0 — surfaces in trace only."
  - "Star count is a noisy community proxy."
  - "Rules-set ecosystems are small in 2026; thresholds may need recalibration as the ecosystem matures."
priorArt:
  - https://github.com/ossf/scorecard/blob/main/docs/checks.md#packaging
---

# SS-RULES-COMMUNITY-INSTALLS-01 — Rules repo with <5 stars

## Rationale

Community-context signal for rules sets (parallel to
SS-SKILL-COMMUNITY-STARS-01). The threshold is lower (5 vs 10) because
the rules-set ecosystem is materially smaller than the skill ecosystem in
2026 — a 5-star threshold approximates the same percentile-position.
Info severity, weight 0: reference context only, no score impact.

## False positive history

(date-stamped log; updated by FP-audit harness and vendor-appeal outcomes)

## Version history

- v1 (Phase A 2026-W2): initial rule. Active at landing as `info` (weight 0).
