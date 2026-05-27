---
ruleId: SS-MCP-SUPPLY-CHAIN-TYPOSQUAT-01
severity: high
subScore: supply_chain
weight: 25
status: shadow
shadowUntil: 2026-W3-end
appliesTo: [mcp]
trigger:
  type: metadata_check
  field: registry_listings_count
  operator: gte
  value: 1
limitations:
  - "v1 is structural — detects MCP servers whose name is within Levenshtein distance 1 of an established registry entry. Distance and the established-set definition land in Phase B engine. Phase A stubs the trigger."
  - "Cannot detect typosquatting where the name is intentionally identical but the org is different (full repo-name collision)."
  - "Cross-registry typosquat detection requires the registries-index population that ships with I-03 (W4)."
priorArt:
  - https://arxiv.org/abs/2002.01139
  - https://socket.dev/blog/typosquatting-attacks
  - https://snyk.io/blog/typosquatting-attacks/
---

# SS-MCP-SUPPLY-CHAIN-TYPOSQUAT-01 — Typosquat candidate (Levenshtein distance ≤1)

## Rationale

Typosquatting in package registries is a documented supply-chain attack
class (Levenshtein-1 attacks on npm, PyPI, and now MCP registries). An MCP
server with a name one character different from an established, trusted
server may be a legitimate fork, a competing implementation, or an
adversarial typosquat hoping a user fat-fingers the install command. The
Socket and Snyk blogs and arXiv 2002.01139 catalogue the prior research on
this attack class.

The v1 rule is structural-only: it identifies MCP names that are within
edit-distance 1 of an established registry entry. The "established" set
definition (which registries count, what star/install threshold qualifies
as "established") and the actual Levenshtein computation land in Phase B
when the engine has the registry-index data. Phase A registers the rule
shape so the Phase B engine can wire the trigger executor.

High severity is appropriate for the supply_chain sub-score: a confirmed
typosquat is a credential-class threat to the agent ecosystem. Shadow
window will quantify FP rate on legitimate forks and competing
implementations.

## False positive history

(date-stamped log; updated by FP-audit harness and vendor-appeal outcomes)

## Version history

- v1 (Phase A 2026-W2): initial rule. Lands shadow; trigger executor in Phase B.
