---
ruleId: SS-HOOKS-SUPPLY-CHAIN-AUTHOR-AGE-01
severity: medium
subScore: supply_chain
weight: 15
status: shadow
shadowUntil: 2026-W3-end
appliesTo: [hooks]
frameworks: ["owasp-llm:llm03", "mitre-atlas:AML.T0010"]
title: >-
  Hook published by a brand-new account
categoryLabel: >-
  Supply chain
explanation: >-
  The account publishing this hook is less than 90 days old. New accounts that publish
  and disappear are a known supply-chain pattern — and a hook runs with your privileges
  automatically, so an unestablished author warrants extra scrutiny before you trust it.
severityRationale: >-
  account age is a weak, secondary signal that account age alone neither proves nor disproves intent.
remediation:
  action: >-
    Weigh this alongside the other supply-chain signals; pin to a reviewed revision before relying on it.
  steps:
    - >-
      Check the author's wider track record rather than judging on account age alone.
    - >-
      Pin to a specific reviewed commit rather than tracking the latest version.
trigger:
  type: metadata_check
  field: owner_age_days
  operator: lt
  value: 90
limitations:
  - "GitHub user account age is a weak signal — long-established accounts can also publish malicious hooks; brand-new accounts publish many legitimate ones."
  - "Does not consider per-user reputation across other repos. v2 may consult OpenSSF reputation signals."
  - "Phase A registers the rule shape; the trigger executor querying GitHub user metadata wires in Phase B."
priorArt:
  - https://socket.dev/blog/supply-chain-attack-targets-tea-token-protocol
  - https://github.com/ossf/scorecard/blob/main/docs/checks.md#packaging
---

# SS-HOOKS-SUPPLY-CHAIN-AUTHOR-AGE-01 — Hook author account <90 days old

## Rationale

A new GitHub user account (<90 days) publishing a hook artifact warrants
extra scrutiny — Socket's 2024 supply-chain analysis documents the
new-account-publish-and-disappear pattern for npm packages, and the
equivalent risk applies to hooks. The signal is noisy (many legitimate
developers create accounts as adults), so we land in shadow.

The Phase A rule registers the shape; the GitHub user-metadata query
wires in Phase B. Shadow window collects FP data on the structural signal.

Medium severity reflects the secondary nature: account age alone is
neither necessary nor sufficient for a supply-chain attack; the signal is
combined with other rules (contributor count, code review presence,
signing) to form an overall supply-chain picture.

## False positive history

(date-stamped log; updated by FP-audit harness and vendor-appeal outcomes)

## Version history

- v1 (Phase A 2026-W2): initial rule. Lands shadow; trigger executor in Phase B.
