---
ruleId: SS-SKILL-MAINTENANCE-CI-BROKEN-01
severity: medium
subScore: maintenance
weight: 12
status: active
shadowUntil: null
appliesTo: [skill, mcp, rules, hooks, plugin]
title: >-
  CI is configured but not enforced on the default branch
categoryLabel: >-
  Maintenance
explanation: >-
  The repository ships a CI workflow file but the default branch has no branch protection requiring
  it to pass. "Has CI" then implies "tests pass on main" when nothing actually enforces that, so a
  green badge can mask regressions merged into the default branch.
severityRationale: >-
  unenforced CI gives a false signal of test discipline while letting failing changes land.
remediation:
  action: >-
    Enable required status checks on the default branch so CI must pass before merge.
  steps:
    - >-
      Turn on branch protection for the default branch.
    - >-
      Mark the CI workflow as a required status check for merges.
  saferPattern:
    before: |-
      # .github/workflows/ci.yml present, but main has no required checks
    after: |-
      # branch protection on `main`:
      #   require status checks to pass before merging → ci
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
a later iteration introduces.

Medium severity is appropriate: the signal is real (broken-but-shipping CI
masks regressions) and the remediation is straightforward (enable required-
status-checks). Active at landing — the v1 composite signal is conservative
and produces few FPs.

## False positive history

(date-stamped log; updated by FP-audit harness and vendor-appeal outcomes)

## Version history

- v1 (2026-01-09): initial rule. Active at landing with structural-signal v1.
