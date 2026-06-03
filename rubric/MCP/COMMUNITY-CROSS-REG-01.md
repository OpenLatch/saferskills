---
ruleId: SS-MCP-COMMUNITY-CROSS-REG-01
severity: info
subScore: community
weight: 0
status: active
shadowUntil: null
appliesTo: [mcp]
title: >-
  Listed on two or more independent MCP registries
categoryLabel: >-
  Community
explanation: >-
  This server appears on at least two independent registries (such as the MCP Registry, Smithery, Glama,
  PulseMCP, or mcp.so), a community-adoption signal that several curators independently chose to list it.
  It's reference context only and does not affect the score.
remediation:
  action: >-
    No action required — context only. Cross-listing is a presence signal, not a guarantee of safety.
trigger:
  type: metadata_check
  field: registry_listings_count
  operator: gte
  value: 2
limitations:
  - "Info severity, weight 0: this rule does NOT affect the score. It surfaces in the trace only as community-presence context."
  - "Requires the Phase B registry-index data to populate the metadata field. v1 lands the rule shape; the trigger executor is wired in Phase B."
  - "Cannot detect registry-listing manipulation (an attacker who lists their MCP across multiple registries inflates the score). The signal is informational only for this reason."
priorArt:
  - https://github.com/modelcontextprotocol/registry
---

# SS-MCP-COMMUNITY-CROSS-REG-01 — MCP listed on ≥2 registries

## Rationale

A presence signal: an MCP server listed on multiple independent registries
(MCP Registry, Smithery, Glama, PulseMCP, mcp.so) has plausibly been
reviewed for inclusion by multiple independent curators, and the
cross-listing is a community-adoption proxy. Info severity at weight 0:
this is reference context for consumers, not a score-affecting signal.

The Phase A landing registers the rule shape; the registry-index data that
populates the `registry_listings_count` field arrives with I-03 (Catalog
Ingestion, W4). Until then, the trigger is registered but does not have
its data source.

The deliberate choice of weight-0 avoids the manipulation risk: an attacker
who cross-lists their hostile MCP cannot use this rule to inflate their
score because the rule has no scoring power. Surfacing the count in the
trace serves consumers without creating an attack incentive.

## False positive history

(date-stamped log; updated by FP-audit harness and vendor-appeal outcomes)

## Version history

- v1 (Phase A 2026-W2): initial rule. Active at landing as `info` (weight 0); data wires in I-03.
