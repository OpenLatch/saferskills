# SaferSkills Detection Rules

Rules land under `rubric/` from W2 (Initiative I-02). Each rule's authoritative shape is a versioned JSON document at `rubric/<rule_id>.json` matching `schemas/detection-rule.schema.json` (which itself lands in W2).

## Rule ID convention

```
SS-<CATEGORY>-<NUMBER>
```

| Token | Allowed values |
|---|---|
| `SS` | Literal prefix |
| `<CATEGORY>` | `MCP-POISON`, `MCP-RUGPULL`, `SKILL`, `SKILL-COLLISION`, `RULES`, `HOOKS`, `PROMPT-INJECT`, `SHELL-RCE`, `SHELL-EXFIL`, `SECRET-EXPOSE`, `SUPPLY-CHAIN`, `PROVENANCE`, `IDENTITY` |
| `<NUMBER>` | Zero-padded 2-digit integer, monotonically allocated per category |

Examples: `SS-MCP-POISON-01` (zero-width Unicode in tool description), `SS-HOOKS-RCE-03` (`curl | bash` in a SessionStart hook command).

## Rule lifecycle

1. **RFC** — open a `03-rule-proposal.yml` issue documenting trigger, severity, FP review, and "what this rule cannot catch".
2. **7-day comment window** — community + maintainer review.
3. **Maintainer decision** — accept / reject / request changes. Decision is a public PR comment with rationale.
4. **PR** — adds `rubric/<rule_id>.json` + a unit test + a fixture pair (positive + negative).
5. **Deprecation** — RFC documenting why; 30-day public notice; removal PR. Deprecated rules stay in git history forever.

Full governance contract: `../.claude/rules/methodology.md`. Public-facing summary: `methodology.md` (this directory).

## Current rule set (W1)

**None.** The W1 repo ships an empty `rubric/` directory. The first rules land W2 (Track B). This file will be regenerated from `rubric/` once the rule set exists.
