---
ruleId: SS-SKILL-TRANSPARENCY-SECURITY-01
severity: low
subScore: transparency
weight: 8
status: active
shadowUntil: null
appliesTo: [skill, mcp, rules, hooks, plugin]
title: >-
  No SECURITY.md disclosure policy in the repository
categoryLabel: >-
  Transparency
explanation: >-
  No <code>SECURITY.md</code> was found (checked the repo root, <code>.github/</code>, and
  <code>docs/</code>). Without one there is no stated way to report a vulnerability, which versions
  are supported, or how quickly the maintainer commits to respond — the baseline for responsible
  disclosure on code that runs in privileged agent contexts.
severityRationale: >-
  with no disclosure policy, a vulnerability has no clear, coordinated path to the maintainer.
remediation:
  action: >-
    Add a SECURITY.md describing how to report vulnerabilities and which versions are supported.
  steps:
    - >-
      Create <code>SECURITY.md</code> (root or <code>.github/</code>) with a disclosure contact.
    - >-
      State supported versions and the response time you commit to.
  saferPattern:
    before: |-
      # no disclosure policy — researchers have nowhere to report
    after: |-
      # SECURITY.md
      ## Reporting a vulnerability
      Email security@example.com. We acknowledge within 72 hours.
trigger:
  type: file_glob_absent
  paths: ['SECURITY.md', '.github/SECURITY.md', 'docs/SECURITY.md']
limitations:
  - "Does not validate SECURITY.md content (presence of disclosure email, response SLA, supported-version table)."
  - "GitHub-Security-Advisory-only disclosure policies are not detected — the rule fires even when the maintainer publishes via GHSA without a file."
priorArt:
  - https://docs.github.com/en/code-security/getting-started/adding-a-security-policy-to-your-repository
  - https://github.com/ossf/scorecard/blob/main/docs/checks.md#security-policy
---

# SS-SKILL-TRANSPARENCY-SECURITY-01 — Missing SECURITY.md disclosure policy

## Rationale

A SECURITY.md file (in any of the canonical locations) declares how a
researcher should disclose a vulnerability found in the artifact, what
versions are supported, and what response SLA the maintainer commits to.
OpenSSF Scorecard codifies this as a baseline security-posture signal; the
GitHub UI surfaces a "Security policy" tab when SECURITY.md is present.

For skills, MCP servers, hooks, plugins, and rule files — all of which run
in privileged agent contexts — a public disclosure policy is the operational
baseline for responsible-disclosure participation. Its absence does not
indicate hostility but does indicate that the project has not prepared for
coordinated disclosure.

Low severity, weight 8: file-presence-only at v1, consistent with the other
Transparency rules. Active at landing — the negative case is unambiguous.

## False positive history

(date-stamped log; updated by FP-audit harness and vendor-appeal outcomes)

## Version history

- v1 (Phase A 2026-W2): initial rule. Active at landing.
