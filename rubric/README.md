<div align="center">

<a href="../README.md">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="../webapp/public/logos/saferskills-dark-wordmark.svg">
    <img alt="SaferSkills" src="../webapp/public/logos/saferskills-light-wordmark.svg" height="38">
  </picture>
</a>

<h3>Detection rules</h3>
<p>The open, versioned scoring rubric — every rule documented, every finding reproducible.</p>

</div>

## What it is

Detection rules live under `rubric/<CATEGORY>/<NAME>-NN.md`. Each file is **Markdown + YAML frontmatter**: the frontmatter carries the machine-readable rule contract (parsed by `scripts/generate-methodology.cjs` and the detector engine); the body carries human-readable rationale, FP history, and version history. The contract is validated against [`../schemas/rubric-rule.schema.json`](../schemas/rubric-rule.schema.json).

Closed-source rules are not allowed — a detection that cannot be described in a `rubric/` doc does not ship.

```
rubric/
├── MCP/      # MCP-server tool-poisoning, capability & supply-chain rules
├── SKILL/    # Claude Code skill rules — prompt-injection, transparency, maintenance
├── HOOKS/    # Claude Code hooks — RCE, dangerous shell, network egress
├── RULES/    # Cursor / Windsurf rule files
├── PLUGIN/   # Claude Code plugin code — credential exfiltration
└── AGENT/    # behavioral Agent Scan pack (AS-NN — a separate taxonomy)
```

## Authoring contract

See [`.claude/rules/methodology.md`](../.claude/rules/methodology.md) § Per-rule contract for the full field-by-field reference. Minimum frontmatter:

```yaml
---
rule_id: SS-<CATEGORY>-<NAME>-NN
severity: info | low | medium | high | critical
sub_score: security | supply_chain | maintenance | transparency | community
weight: 0..40
status: shadow | active | deprecated
shadow_until: 2026-01-18       # required iff status: shadow
applies_to: [skill, mcp, rules, hooks, plugin]   # subset
title: …                        # plain-English finding headline (no rule_id)
explanation: …                  # the "why it matters" paragraph
remediation:
  action: …                     # imperative one-liner
trigger:
  type: regex_match | file_glob_present | file_glob_absent | commit_history_check | metadata_check | composite_and_or
  ...
limitations:
  - "Cannot detect ..."
prior_art:
  - https://...
---
```

## Rule lifecycle

A rule lands only after: an open [`03-rule-proposal.yml`](../.github/ISSUE_TEMPLATE/03-rule-proposal.yml) RFC → a 7-day public comment window → a maintainer accept → a PR adding the rule doc + trigger config.

Every rule lands with `status: shadow` + `shadow_until: <T+7d>` regardless of author confidence: the detector fires and records findings in the scan trace, but the rule's weight is 0 (no score impact) during the shadow window. After 7 days the FP-audit harness ([`tools/fp-audit/`](../tools/fp-audit/README.md)) gates promotion — <10% FP rate → `status: active`; ≥10% → `shadow_until` extended +7d with maintainer review.

## See also

- [`contributor-docs/methodology.md`](../contributor-docs/methodology.md) — public-facing summary
- [`contributor-docs/rules.md`](../contributor-docs/rules.md) — rule-ID convention + lifecycle
- [`.claude/rules/methodology.md`](../.claude/rules/methodology.md) — contributor-facing detail

---

<sub>Part of **[SaferSkills](../README.md)** — every AI capability, independently scanned. · An [OpenLatch](https://openlatch.ai) project · [saferskills.ai](https://saferskills.ai)</sub>
