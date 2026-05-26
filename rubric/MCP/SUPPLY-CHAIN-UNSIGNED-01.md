---
ruleId: SS-MCP-SUPPLY-CHAIN-UNSIGNED-01
severity: medium
subScore: supply_chain
weight: 12
status: shadow
shadowUntil: 2026-W3-end
appliesTo: [mcp]
trigger:
  type: file_glob_absent
  paths: ['**/*.sig', '**/*.minisig', '**/cosign.pub', '**/SIGNATURES', '**/.signatures.yaml']
limitations:
  - "Most MCP servers in 2026 do not sign releases — the rule will fire on the majority of the catalog. Shadow window quantifies whether this matters operationally."
  - "Detects file-presence only; does not validate signatures or verify a trust chain."
  - "GitHub-Actions-signed-only releases (Sigstore via attestations) are not detected without a Sigstore API query. v2 enhancement."
priorArt:
  - https://www.sigstore.dev/
  - https://www.openssf.org/blog/2022/03/15/breaking-down-the-state-of-software-supply-chain-security-with-our-2022-report/
---

# SS-MCP-SUPPLY-CHAIN-UNSIGNED-01 — Unsigned MCP release

## Rationale

Cryptographic signing of releases (Sigstore, GPG, minisign) closes the
supply-chain class of "someone replaced the tarball" attacks. An MCP server
without any signature file in the repo is unsigned by the file-presence
check; the consumer cannot verify that the install bytes match what the
maintainer published.

The Phase A landing is shadow because the operational reality of the MCP
ecosystem in 2026 is that most servers are unsigned. We need real audit
data on whether this rule (a) provides useful signal even when most fire
positive, or (b) functions essentially as a "the ecosystem is immature"
signal that should be info-severity rather than score-affecting.

Medium severity is the v1 placeholder; the shadow-window data informs
whether to promote at medium, demote to info (no score impact), or refine
the trigger to only fire on repos that *should* have signed releases (high
star count, security-sensitive category).

## False positive history

(date-stamped log; updated by FP-audit harness and vendor-appeal outcomes)

## Version history

- v1 (Phase A 2026-W2): initial rule. Lands shadow pending ecosystem-maturity data.
