# SaferSkills Detection Rules

Detection rules live under `rubric/<CATEGORY>/<NAME>-NN.md` (locked decision **D-04**). Each rule's authoritative shape is the YAML frontmatter validated against [`../schemas/rubric-rule.schema.json`](../schemas/rubric-rule.schema.json); the body is Markdown rationale + FP history + version history.

## Rule ID convention

Per locked decision **D-03** and [`../.claude/rules/naming-conventions.md`](../.claude/rules/naming-conventions.md) § Rule IDs:

```
SS-<CATEGORY>-<NAME>-<NN>
```

| Token | Allowed values |
|---|---|
| `SS` | Literal prefix (distinguishes SaferSkills rules from imported third-party detector vocabularies) |
| `<CATEGORY>` | Closed enum: `MCP`, `SKILL`, `RULES`, `HOOKS`, `PLUGIN` |
| `<NAME>` | Uppercase kebab-case, e.g. `POISON-UNICODE-TAG`, `INJECT-FENCED-RUN`, `RCE-CURL-PIPE` |
| `<NN>` | Two-digit zero-padded sequence, monotonically allocated per `<CATEGORY>-<NAME>` |

Regex (enforced in `rubric-rule.schema.json` and `finding.schema.json`):

```
^SS-(MCP|SKILL|RULES|HOOKS|PLUGIN)-[A-Z][A-Z0-9-]*-\d{2}$
```

Examples: `SS-MCP-POISON-UNICODE-TAG-01`, `SS-SKILL-INJECT-FENCED-RUN-01`, `SS-HOOKS-RCE-CURL-PIPE-01`, `SS-PLUGIN-SECRET-EXFIL-GH-TOKEN-01`.

## Severity ladder

5-tier per locked decision **D-02**:

```
info | low | medium | high | critical
```

`info` carries weight 0 — advisory only; surfaces in the scan trace but does not affect the score. See [`methodology.md`](methodology.md) § Scoring model for per-tier penalty ranges and critical-floor application.

## Sub-score axes

5-axis per locked decision **D-01**:

```
security | supply_chain | maintenance | transparency | community
```

Each rule's frontmatter assigns it to exactly one sub-score. The sub-score weights (35/20/15/15/15) are PRD-locked.

## Trigger primitives

The 6 primitive trigger types `rubric-rule.schema.json` accepts:

| Primitive | Use for |
|---|---|
| `regex_match` | Pattern matching against file contents |
| `file_glob_present` | Rule fires if any matching file exists |
| `file_glob_absent` | Rule fires if NO matching file exists |
| `commit_history_check` | Commit-level signals (recency, frequency, contributors) |
| `metadata_check` | Repo metadata (stars, license, branch protection) |
| `composite_and_or` | Boolean composition of other primitives |

Adding a new primitive requires an RFC (see § Rule lifecycle).

## Rule lifecycle

```
RFC (issue) → 7-day public comment window → maintainer decision
                                          ↓ if accepted
                          PR lands rubric/<CATEGORY>/<NAME>-NN.md
                                          ↓
                              status: shadow + shadow_until: T+7d
                                          ↓
                       FP-audit harness (tools/fp-audit/) measures FP rate
                                          ↓
                  ┌─── FP rate < 10% ────┴──── FP rate ≥ 10% ────┐
                  ↓                                                ↓
            status: active                       shadow_until extended +7d
                  ↓                                                ↓
               (live)                              maintainer-led trigger refinement
                  ↓
       ── deprecation RFC → 30-day public notice → removal PR
```

Every rule lands with `status: shadow` regardless of author confidence — the FP-audit harness is the only promotion mechanism. Deprecated rules stay in git history forever; historical scans must remain explainable.

Full governance contract: [`../.claude/rules/methodology.md`](../.claude/rules/methodology.md).

## Current rule set (Phase A — W2)

The first batch of **55 rules** ships with this document:

- **SKILL** (25) — prompt-injection (13), transparency (5), maintenance (5), community (2)
- **MCP** (10) — poisoning (5), capability (1), supply-chain (3), community (1)
- **HOOKS** (10) — RCE (5), obfuscation (2), supply-chain (2), community (1)
- **RULES** (5) — injection (1), obfuscation (2), transparency (1), community (1)
- **PLUGIN** (5) — credential exfiltration (5)

Active vs Shadow split: 32 active / 23 shadow at landing. Promotion of shadow rules to active is gated by the 7-day FP-audit window.

The live, auto-rendered list with full frontmatter is at [`https://saferskills.ai/methodology`](https://saferskills.ai/methodology) — generated from `rubric/` by codegen step #7 (`scripts/generate-methodology.cjs`).

## Per-rule contract

Every rule's frontmatter MUST contain:

- `rule_id` (`SS-<CATEGORY>-<NAME>-NN` regex)
- `severity` (5-tier)
- `sub_score` (5-axis)
- `weight` (0–40)
- `status` (`shadow` / `active` / `deprecated`)
- `shadow_until` (required iff `status: shadow`)
- `applies_to` (array; subset of `[skill, mcp, rules, hooks, plugin]`)
- `trigger` (one of the 6 primitives)
- `limitations` (non-empty array — what the rule cannot catch)
- `prior_art` (array of URLs to CVEs / OWASP entries / research papers)

The body sections are conventional (`## Rationale`, `## False positive history`, `## Version history`) but not enforced beyond the frontmatter.
