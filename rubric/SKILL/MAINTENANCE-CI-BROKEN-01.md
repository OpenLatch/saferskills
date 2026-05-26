---
ruleId: SS-SKILL-MAINTENANCE-CI-BROKEN-01
severity: medium
subScore: maintenance
weight: 12
status: active
shadowUntil: null
appliesTo: [skill, mcp, rules, hooks, plugin]
trigger:
  type: composite_and_or
  op: and
  children:
    - type: file_glob_present
      paths: ['.github/workflows/*.yml', '.github/workflows/*.yaml', '.gitlab-ci.yml', '.circleci/config.yml']
    - type: metadata_check
      field: default_branch_protected
      operator: exists
      value: true
limitations:
  - "Cannot distinguish a CI configuration that legitimately allows main-branch failures (e.g. nightly canary jobs that exercise unstable upstream code) from one that simply isn't enforced."
  - "v1 detects the *presence* of a workflow file as the signal; v2 will query the GitHub Actions API to check recent default-branch run conclusions."
  - "Cannot detect CI hosted off-platform (Buildkite-hosted, self-hosted Jenkins) when no in-repo workflow file exists."
priorArt:
  - https://github.com/ossf/scorecard/blob/main/docs/checks.md#ci-tests
  - https://chaoss.community/kb/metric-ci-builds/
---

# SS-SKILL-MAINTENANCE-CI-BROKEN-01 — CI configured but unenforced

## Rationale

A repository that ships a CI workflow file but doesn't enforce passing CI on
the default branch creates a false signal of test discipline — consumers
expect that "has CI" implies "tests pass on main", which the absence of
branch protection doesn't guarantee. OpenSSF Scorecard's "CI-Tests" check
codifies this as a baseline maintenance signal.

v1 detects the structural condition (workflow file present + branch
protection absent or unconfigured) using the GitHub metadata. v2 will
extend with a GitHub Actions API query to check whether recent default-branch
runs actually pass; that requires API tokens and rate-limit budget that
Phase B introduces.

Medium severity is appropriate: the signal is real (broken-but-shipping CI
masks regressions) and the remediation is straightforward (enable required-
status-checks). Active at landing — the v1 composite signal is conservative
and produces few FPs.

## False positive history

(date-stamped log; updated by FP-audit harness and vendor-appeal outcomes)

## Version history

- v1 (Phase A 2026-W2): initial rule. Active at landing with structural-signal v1.
