---
ruleId: SS-PLUGIN-SECRET-EXFIL-GH-TOKEN-01
severity: critical
subScore: security
weight: 35
status: active
shadowUntil: null
appliesTo: [plugin]
frameworks: ["owasp-llm:llm02", "mitre-atlas:AML.T0025", "cwe:798"]
title: >-
  Contains a committed GitHub token
categoryLabel: >-
  Credential exfiltration
explanation: >-
  A GitHub token ({match}) is committed directly into this plugin's source. Anyone
  who reads the repo — including everyone who installs the plugin — gets the token,
  so it must be treated as already compromised.
severityRationale: >-
  a committed token is exposed the moment it lands on a public repo — the
  credential is leaked outright, not merely at risk.
remediation:
  action: >-
    Revoke the leaked token immediately, then remove it from the code and from
    Git history.
  steps:
    - >-
      Revoke the token in GitHub settings now — anything pushed is already public.
    - >-
      Delete it from the source and purge it from history; load credentials at
      runtime from the environment or a secrets store instead.
  saferPattern:
    before: |-
      GITHUB_TOKEN = "ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
    after: |-
      # never commit the token; read it at runtime from the environment
      GITHUB_TOKEN = os.environ["GITHUB_TOKEN"]
trigger:
  type: regex_match
  pattern: '\b(?:ghp_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{82}|gho_[A-Za-z0-9]{36}|ghu_[A-Za-z0-9]{36}|ghs_[A-Za-z0-9]{36}|ghr_[A-Za-z0-9]{36})\b'
  scope:
    paths: ['**/*.py', '**/*.ts', '**/*.js', '**/*.mjs', '**/*.cjs', '**/*.go', '**/*.rb', '**/*.java', '**/*.md', '**/*.json', '**/*.yaml', '**/*.yml']
limitations:
  - "Detects only the canonical GitHub token prefixes (ghp_ / github_pat_ / gho_ / ghu_ / ghs_ / ghr_). Cannot detect legacy 40-char hex tokens without high FP risk."
  - "Detects committed tokens; cannot detect tokens read at runtime from env or from external secrets store."
  - "Cannot distinguish revoked / expired tokens from active ones."
priorArt:
  - https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/about-authentication-with-saml-single-sign-on
  - https://docs.github.com/en/code-security/secret-scanning/secret-scanning-patterns
  - https://github.com/secretlint/secretlint
---

# SS-PLUGIN-SECRET-EXFIL-GH-TOKEN-01 — Committed GitHub token

## Rationale

A GitHub Personal Access Token, OAuth token, server-to-server token, or
refresh token committed into a plugin's source code is an immediate
credential exposure: any consumer who installs the plugin obtains the
token, and the token is publicly readable on GitHub. GitHub's own
secret-scanning service uses the same canonical prefix patterns the rule
detects.

Critical severity is unambiguous: a committed token is already compromised
the moment it lands on a public repo. The rule's job is to flag it before
or at the moment of catalog ingestion so the consumer sees the warning
before installing.

Active at landing — the canonical-prefix pattern set has near-zero FP rate.

## False positive history

(date-stamped log; updated by FP-audit harness and vendor-appeal outcomes)

## Version history

- v1 (2026-01-09): initial rule. Active at landing.
