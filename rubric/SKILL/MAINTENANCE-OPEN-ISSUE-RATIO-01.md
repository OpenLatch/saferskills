---
ruleId: SS-SKILL-MAINTENANCE-OPEN-ISSUE-RATIO-01
severity: low
subScore: maintenance
weight: 8
status: shadow
shadowUntil: 2026-01-18
appliesTo: [skill, mcp, rules, hooks, plugin]
title: >-
  Over 80% of opened issues remain open
categoryLabel: >-
  Maintenance
explanation: >-
  Across a 12-month window, more than 80% of opened issues are still open (open / (open + closed)).
  That suggests issues are being filed faster than they get resolved, so a report you file may sit
  unresolved.
severityRationale: >-
  a high unresolved-issue backlog suggests your bug report is likely to stay open.
remediation:
  action: >-
    Work down the open-issue backlog and close or resolve stale reports.
  steps:
    - >-
      Triage long-open issues, closing duplicates and ones that are won't-fix.
    - >-
      Keep the close rate roughly in step with the rate new issues arrive.
trigger:
  type: commit_history_check
  signal: open_issue_ratio
  operator: gt
  threshold: 0.8
limitations:
  - "Repositories with issues disabled produce no signal."
  - "Stale-but-not-resolved issues (legitimate edge cases, won't-fix, deferred) inflate the ratio. v2 will require ≥30 days of inactivity on the open issue before counting."
  - "Repositories with a large historical issue backlog from a different maintainer era unfairly accumulate ratio. v2 may consider a rolling 12-month window."
priorArt:
  - https://chaoss.community/kb/metric-issues-active/
---

# SS-SKILL-MAINTENANCE-OPEN-ISSUE-RATIO-01 — >80% of opened issues remain open

## Rationale

A high open-issue ratio (open / (open + closed)) over a 12-month window
indicates that issues are being filed faster than the maintainer can
resolve them. Combined with the other Maintenance signals, this paints a
picture of a project struggling to keep pace with its own bug surface.

The 0.8 threshold is conservative; values of 0.5-0.7 are normal for
actively-developed projects. Shadow window will quantify the cost and
inform whether to refine the metric (rolling window, ignoring `won't-fix`
labels, etc.) before promotion.

Low severity per the Maintenance-tier convention. Lands shadow.

## False positive history

(date-stamped log; updated by FP-audit harness and vendor-appeal outcomes)

## Version history

- v1 (2026-01-09): initial rule. Lands shadow; FP-audit gates promotion.
