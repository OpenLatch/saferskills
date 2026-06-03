---
ruleId: SS-SKILL-MAINTENANCE-COMMIT-FREQ-01
severity: low
subScore: maintenance
weight: 8
status: shadow
shadowUntil: 2026-W3-end
appliesTo: [skill, mcp, rules, hooks, plugin]
title: >-
  Fewer than 3 commits in the last 90 days
categoryLabel: >-
  Maintenance
explanation: >-
  The default branch saw fewer than three commits in the trailing 90 days. Read alongside the
  last-commit-age signal, low recent activity suggests the project may not keep pace with bug
  reports or dependency updates.
severityRationale: >-
  low recent commit volume signals limited capacity to ship fixes promptly.
remediation:
  action: >-
    Maintain a steadier commit cadence, or document that the project is in maintenance-only mode.
  steps:
    - >-
      Land outstanding fixes and dependency bumps rather than batching them indefinitely.
    - >-
      If activity is low by design, note the maintenance status in the README.
trigger:
  type: commit_history_check
  signal: commit_freq_90d
  operator: lt
  threshold: 3
limitations:
  - "FP rate on stable mature libraries is real (a finished library may have <3 commits in 90 days as a sign of stability, not abandonment). Shadow window measures the cost."
  - "Bot commits (dependabot, renovate) inflate the count without indicating maintainer engagement. v2 may exclude bot-authored commits from the signal."
  - "Cannot distinguish commit-volume from commit-significance (a single substantial commit vs three trivial ones)."
priorArt:
  - https://github.com/ossf/scorecard/blob/main/docs/checks.md#maintained
  - https://chaoss.community/kb/metric-code-changes/
---

# SS-SKILL-MAINTENANCE-COMMIT-FREQ-01 — <3 commits in trailing 90 days

## Rationale

Commit frequency in the trailing 90-day window is a secondary maintenance
signal — independent of and complementary to the absolute-staleness check
(SS-SKILL-MAINTENANCE-COMMIT-RECENCY-01). A repository with one commit in
the last 360 days passes the recency check but fails this frequency check;
the inverse holds for a project with a recent commit but otherwise
infrequent activity. The combination yields a more nuanced maintenance
signal than either alone.

The 3-commit / 90-day threshold is conservative — chosen to suppress FP on
stable single-maintainer projects with periodic release cadences. Shadow
window will quantify the FP rate; if too high, the v2 path is to either
raise the threshold or weight the signal by repo size (smaller repos
legitimately have lower commit volume).

Low severity, weight 8: complementary signal, not standalone determinative.
Lands shadow; the FP audit decides promotion.

## False positive history

(date-stamped log; updated by FP-audit harness and vendor-appeal outcomes)

## Version history

- v1 (Phase A 2026-W2): initial rule. Lands shadow; FP-audit gates promotion.
