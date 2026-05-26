---
ruleId: SS-SKILL-MAINTENANCE-ISSUE-RESPONSE-01
severity: low
subScore: maintenance
weight: 8
status: shadow
shadowUntil: 2026-W3-end
appliesTo: [skill, mcp, rules, hooks, plugin]
trigger:
  type: commit_history_check
  signal: issue_response_p50_hours
  operator: gt
  threshold: 720
limitations:
  - "Repositories with issues disabled (Issues feature off) produce no signal; the rule does not fire on those."
  - "Median is sensitive to small sample sizes (n<5 issues in window). v2 will require ≥5 issues for the signal to register."
  - "Counts ANY maintainer comment as a response; cannot distinguish substantive engagement from a triage acknowledgment."
priorArt:
  - https://chaoss.community/kb/metric-issues-response-time/
  - https://github.com/ossf/scorecard/blob/main/docs/checks.md#maintained
---

# SS-SKILL-MAINTENANCE-ISSUE-RESPONSE-01 — Median issue response >30 days

## Rationale

Issue response latency is a direct measure of maintainer engagement. A
median first-response time exceeding 30 days (720 hours) on issues opened in
the last 12 months indicates that bug reports — including security reports —
are unlikely to be addressed promptly. The CHAOSS "Issues Response Time"
metric is the canonical formulation.

The shadow window will quantify the false-positive cost. Known weaknesses
in the v1 signal: small sample sizes (n<5 issues) produce noisy medians; the
"any-maintainer-comment counts" definition over-counts triage labels as real
engagement. Both will be addressed in v2 alongside promotion.

Low severity reflects the complementary nature: combined with stale-commit
and infrequent-commit findings, an issue-response delay paints a coherent
maintenance-failure picture; alone, it is a soft signal subject to noise.

## False positive history

(date-stamped log; updated by FP-audit harness and vendor-appeal outcomes)

## Version history

- v1 (Phase A 2026-W2): initial rule. Lands shadow; FP-audit gates promotion.
