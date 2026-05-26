# rubric/ — SaferSkills detection rules

Detection rules live under `rubric/<CATEGORY>/<NAME>-NN.md` per locked decision D-04.
Each file is **Markdown + YAML frontmatter**: the frontmatter carries the machine-readable
rule contract (parsed by `scripts/generate-methodology.cjs` and the W2+ detector engine);
the body carries human-readable rationale, FP history, and version history.

The rule contract is validated against [`../schemas/rubric-rule.schema.json`](../schemas/rubric-rule.schema.json).

```
rubric/
├── MCP/      (MCP-server-specific tool poisoning + capability + supply-chain rules)
├── SKILL/    (Claude Code skill rules — prompt-injection, transparency, maintenance)
├── HOOKS/    (Claude Code hooks — RCE, dangerous shell, network egress)
├── RULES/    (Cursor / Windsurf rule files)
└── PLUGIN/   (Claude Code plugin code — credential exfiltration)
```

## Authoring contract

See [`.claude/rules/methodology.md`](../.claude/rules/methodology.md) § Per-rule contract for the
full field-by-field reference. Minimum frontmatter:

```yaml
---
rule_id: SS-<CATEGORY>-<NAME>-NN
severity: info | low | medium | high | critical
sub_score: security | supply_chain | maintenance | transparency | community
weight: 0..40
status: shadow | active | deprecated
shadow_until: 2026-W3-end       # required iff status: shadow
applies_to: [skill, mcp, rules, hooks, plugin]   # subset
trigger:
  type: regex_match | file_glob_present | file_glob_absent | commit_history_check | metadata_check | composite_and_or
  ...                          # primitive-specific params
limitations:
  - "Cannot detect ..."
prior_art:
  - https://...
---
```

## Rule lifecycle

A rule lands only after:

1. An open `.github/ISSUE_TEMPLATE/03-rule-proposal.yml` RFC
2. A 7-day public comment window
3. A maintainer accept decision
4. A PR adding `rubric/<CATEGORY>/<NAME>-NN.md` + the trigger config validated by `schemas/rubric-rule.schema.json`

Every rule lands with `status: shadow` + `shadow_until: <T+7d>` regardless of author
confidence. The detector fires + records findings in the scan trace, but the rule's
weight is 0 (no score impact) during the shadow window. After 7 days, the FP-audit
harness (`tools/fp-audit/`) gates promotion: <10% FP rate → `status: active`; ≥10% →
`shadow_until` extended +7d with maintainer review.

## Reference

- [`docs/methodology.md`](../docs/methodology.md) — public-facing summary
- [`docs/rules.md`](../docs/rules.md) — rule-ID convention + lifecycle
- [`.claude/rules/methodology.md`](../.claude/rules/methodology.md) — contributor-facing detail
