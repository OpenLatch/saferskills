---
ruleId: SS-SKILL-MAINTENANCE-COMMIT-RECENCY-01
severity: medium
subScore: maintenance
weight: 12
status: active
shadowUntil: null
appliesTo: [skill, mcp, rules, hooks, plugin]
trigger:
  type: commit_history_check
  signal: last_commit_age_days
  operator: gt
  threshold: 365
limitations:
  - "Mature, finished libraries that legitimately need no recent updates trigger this rule. The Maintenance sub-score weight (15%) limits the impact — a stable mature library still scores well overall."
  - "Cannot distinguish an abandoned project from a stable one without external signals (issue response time, release cadence). The composite signal is split across multiple Maintenance rules."
  - "Repository default-branch commit age only — branch-specific staleness is not assessed."
priorArt:
  - https://github.com/ossf/scorecard/blob/main/docs/checks.md#maintained
  - https://chaoss.community/kb/metric-time-since-last-commit/
---

# SS-SKILL-MAINTENANCE-COMMIT-RECENCY-01 — Default branch stale >365 days

## Rationale

Default-branch commit recency is a canonical maintenance signal codified by
OpenSSF Scorecard's "Maintained" check and the CHAOSS metrics catalogue. A
year of no commits on the default branch indicates either abandonment or a
finished library that has reached steady-state. The Maintenance sub-score
weight (15% aggregate) limits the impact — a single stale-commit finding
reduces the sub-score but does not collapse the overall trust score for a
stable mature library.

The 365-day threshold is conservative; OpenSSF Scorecard uses a 90-day
window in its strictest tier. We chose 365 to suppress FP on legitimate
slow-moving but maintained projects while still catching abandonment.

Medium severity is appropriate for the Maintenance class: the signal is real
(stale code accumulates unfixed CVEs and compatibility drift) but not in
itself adversarial. Active at landing — the signal is unambiguous when it
fires.

## False positive history

(date-stamped log; updated by FP-audit harness and vendor-appeal outcomes)

## Version history

- v1 (Phase A 2026-W2): initial rule. Active at landing with 365-day threshold.
