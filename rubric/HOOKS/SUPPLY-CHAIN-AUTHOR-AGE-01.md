---
ruleId: SS-HOOKS-SUPPLY-CHAIN-AUTHOR-AGE-01
severity: medium
subScore: supply_chain
weight: 15
status: shadow
shadowUntil: 2026-W3-end
appliesTo: [hooks]
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
