---
paths:
  - "docs/methodology.md"
  - "docs/rules.md"
  - "rubric/**"
---

# Methodology — open scoring rubric + rule-RFC governance

> **Paths**: `docs/methodology.md`, `docs/rules.md`, `rubric/**`
> **Public-facing summary**: `docs/methodology.md` (repo root). This rule is the contributor-facing detail; the two MUST stay in sync.

## Purpose

SaferSkills' credibility rests on a public, deterministic, auditable scoring rubric. Every finding the platform publishes is traceable to a specific rule documented in `rubric/`, and every vendor whose artifact is scored has a right to verify which rule version flagged them (cf. `vendor-appeals.md`).

**Closed-source rules are not allowed.** A detection that we cannot describe in a `rubric/<category>/<name>.md` does not ship.

## File layout

```
rubric/
├── MCP/
│   ├── POISON-UNICODE-TAG-01.md
│   ├── POISON-DESCRIPTION-CREEP-01.md
│   ├── SUPPLY-CHAIN-HASH-DRIFT-01.md
│   └── ...
├── SKILL/
│   ├── INJECT-UNICODE-TAG-01.md
│   ├── INJECT-FENCED-RUN-01.md
│   └── ...
├── RULES/
│   ├── INJECT-IMPERATIVE-01.md
│   └── ...
├── HOOKS/
│   ├── RCE-CURL-PIPE-01.md
│   └── ...
└── PLUGIN/
    ├── SECRET-EXFIL-GH-TOKEN-01.md
    └── ...
```

Each `rubric/<CATEGORY>/<NAME>-NN.md` is **Markdown + YAML frontmatter** (per locked decision D-04). The frontmatter carries the machine-readable rule contract (parsed by `scripts/generate-methodology.cjs` + the W2 detector engine); the body carries human-readable rationale, FP history, and version history.

## Per-rule contract

Every `rubric/<CATEGORY>/<NAME>-NN.md` MUST carry the following YAML frontmatter (validated against `schemas/rubric-rule.schema.json`):

| Field | Required | Content |
|---|---|---|
| `rule_id` | yes | `SS-<CATEGORY>-<NAME>-NN` (per `naming-conventions.md` § Rule IDs) |
| `severity` | yes | One of `info` / `low` / `medium` / `high` / `critical` (5-tier per locked decision D-02). `info` carries weight 0 — advisory only |
| `sub_score` | yes | One of `security` / `supply_chain` / `maintenance` / `transparency` / `community` (5-axis per locked decision D-01) |
| `weight` | yes | Integer 0–40. Maximum penalty this rule contributes to its sub-score |
| `status` | yes | One of `shadow` / `active` / `deprecated` (per locked decision D-14) |
| `shadow_until` | iff `status: shadow` | ISO date (e.g. `2026-W3-end`) when the FP-audit harness re-evaluates promotion |
| `applies_to` | yes | Array; subset of `[skill, mcp, rules, hooks, plugin]` |
| `trigger` | yes | One of the 6 primitive types (`regex_match`, `file_glob_present`, `file_glob_absent`, `commit_history_check`, `metadata_check`, `composite_and_or`). Closed set; new primitives require an RFC |
| `limitations` | yes | What the rule cannot catch. **Mandatory** — no rule ships without limitations. Non-empty list |
| `prior_art` | yes | Array of URLs to CVEs, research papers, OWASP entries, vendor write-ups that motivate the rule |

Body sections (human-readable, not enforced):

| Section | Content |
|---|---|
| `# <rule_id> — <human title>` | Top-level heading |
| `## Rationale` | Why this is a security/quality concern. Cite prior art inline |
| `## False positive history` | Date-stamped log of FP reports + how they were resolved (kept; never redacted) |
| `## Version history` | Per-version changelog (additive only; old behavior re-derivable from git) |

## Scoring is deterministic

- **Same input → same score**, byte-for-byte. The rubric version is part of the scan input.
- Every scan report records its `rubric_version` (git SHA of `rubric/` at scan time) in the response payload.
- A vendor can verify a finding by running the exact `rubric_version` against the exact artifact bytes at the recorded `ref_sha` — the result is reproducible without platform participation. (The **stored snapshot** — `artifact_blobs`, see `database.md` — preserves those exact text-file bytes, so reproduction needs no re-fetch; it is a storage feature, **not** part of the verdict path and **never** an input to scoring.)
- **No LLM in the verdict path.** No probabilistic scoring. No editorial moderation queue. Hard, structural.
- **No randomness, no ML-as-a-black-box.** Heuristics may use ML-trained classifiers, but the classifier weights ship versioned under `rubric/<CATEGORY>/_models/` and the rule doc names which model version it uses.

## Sub-scores and aggregate (locked D-01 / D-02 / D-13)

5-axis sub-score taxonomy, with PRD-locked weights:

| Sub-score key | Weight | What it measures |
|---|---|---|
| `security` | 35% | Prompt injection, obfuscation, dangerous shell, credential exfiltration |
| `supply_chain` | 20% | Typosquat, owner-transfer, hash-drift, unsigned, transitive risk |
| `maintenance` | 15% | Commit recency, commit frequency, issue response time, CI health |
| `transparency` | 15% | Manifest / LICENSE / CHANGELOG / SECURITY.md presence + description quality |
| `community` | 15% | Stars, contributors, cross-registry presence, fork health |

5-tier severity ladder with sub-score penalty ranges:

| Severity | Penalty range | Notes |
|---|---|---|
| `critical` | −30 to −40 | Triggers critical-floor: sub_score capped at 40 |
| `high` | −20 to −30 | |
| `medium` | −10 to −20 | |
| `low` | −5 to −10 | |
| `info` | 0 | Advisory-only; surfaces in trace, no score impact |

`sub_score = max(0, 100 − Σ penalty_i)`. If any finding in a sub-score has `severity: critical`, the sub-score is capped: `sub_score = min(sub_score, 40)`. Aggregate = `Σ sub_score × weight`.

Every public scan report renders the **explicit breakdown**: per-finding penalty, running sub-score, critical-floor application, weighted aggregate, tier-band mapping. See the `score_breakdown` block in `schemas/scan-report.schema.json`.

## Rule-RFC workflow

New rules and rule changes go through a public RFC:

1. **Open issue** via `.github/ISSUE_TEMPLATE/03-rule-proposal.yml`. Title format: `RFC: SS-<CATEGORY>-<NAME>-NN — <short description>`.
2. **7-day comment window** — public can leave comments; maintainer labels with `rfc/discussion`.
3. **Maintainer decision** at end of window: `rfc/accepted` → proceed to PR; `rfc/rejected` → close with a substantive rationale in a final comment; `rfc/needs-changes` → extend the window once.
4. **Implementation PR** adds `rubric/<CATEGORY>/<NAME>-NN.md` + the detector trigger config (frontmatter only at W2 Phase A; trigger executors land Phase B under `services/api/app/scan/triggers/`) + tests. The PR description links the RFC issue.
5. **Activation** is two-stage: the PR lands with `status: shadow` + `shadow_until: <T+7d>` regardless of how confident the author is. The detector fires + records findings in the scan trace, but the rule's weight is 0 (no score impact) during the shadow window. After 7 days the FP-audit harness (`tools/fp-audit/`) gates promotion: <10% FP rate → `status: active`; ≥10% → `shadow_until` extended +7d with maintainer review. See `.claude/rules/testing.md` for the FP-audit harness contract.

## Deprecation policy

Rules are **never silently retired**. A deprecation:

1. Opens an RFC labeled `rfc/deprecate`.
2. On acceptance, the rule's doc gains a `deprecated_in_version: <semver>` field and a `deprecation_rationale` section.
3. The detector keeps running for **one minor version** with `severity_tier: low` and a "deprecation pending" annotation on every finding.
4. The next minor version removes the detector code but keeps the rule doc forever — historical scans must remain explainable.

## Limitations — every rule

Every rule's `limitations` frontmatter field names what it cannot catch. Examples:

- `SS-MCP-POISON-UNICODE-TAG-01.limitations`: "Cannot detect tag-channel characters re-encoded as numeric entities (`&#xE0001;`); rule operates on decoded text only."
- `SS-HOOKS-RCE-CURL-PIPE-01.limitations`: "Cannot detect obfuscated shell-RCE via runtime string concatenation; rule operates on static pattern match."

**No black-box findings.** A finding that names a rule must be reproducible from the rule's documented trigger.

## Hard rules

1. **Every rule is publicly documented** under `rubric/`. Closed-source rules do not ship.
2. **Every rule has a `limitations` section.** Mandatory.
3. **Scoring is deterministic** — same input + same `rubric_version` → same score.
4. **Rule-RFC for additions + changes.** 7-day comment window minimum.
5. **No silent retirements.** Deprecation goes through the documented policy.
6. **`docs/methodology.md` (root, public) and this rule stay in sync.** Public-facing changes ship in both.

## When to update this rule

| Change | Updates here |
|---|---|
| New rule category | "File layout" + `naming-conventions.md` Rule IDs |
| New per-rule contract field | "Per-rule contract" table + `schemas/rubric-rule.schema.json` + every existing rubric doc backfilled in the same PR |
| New trigger primitive | "Per-rule contract" `trigger` row + `schemas/rubric-rule.schema.json` + RFC |
| New sub-score axis | "Sub-scores and aggregate" + `schemas/scan-report.schema.json` + PRD §5.2 |
| New severity tier | "Sub-scores and aggregate" + `schemas/rubric-rule.schema.json` + `schemas/finding.schema.json` |
| Rule-RFC workflow change | "Rule-RFC workflow" + `.github/ISSUE_TEMPLATE/03-rule-proposal.yml` |
| Deprecation policy change | "Deprecation policy" + every rule mid-deprecation reviewed |
| Scoring determinism change (e.g. new ML model integration) | "Scoring is deterministic" — re-verify the same-input-same-score invariant |
