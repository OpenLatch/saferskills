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
│   ├── POISON-UNICODE-01.md
│   ├── POISON-IMPERATIVE-01.md
│   ├── RUGPULL-01.md
│   └── ...
├── SKILL/
│   ├── INJECT-UNICODE-01.md
│   ├── INJECT-FENCED-RUN-01.md
│   └── ...
├── RULES/
│   ├── INJECT-DETAILS-01.md
│   └── ...
├── HOOKS/
│   ├── RCE-01.md
│   └── ...
└── PLUGIN/
    └── ...
```

Each `<RULE>.md` carries the contract below.

## Per-rule contract

Every `rubric/<category>/<name>-NN.md` MUST contain:

| Section | Content |
|---|---|
| `rule_id` | `SS-<CATEGORY>-<NAME>-NN` (per `naming-conventions.md` Rule IDs) |
| `trigger` | Plain-English description of what fires the rule, plus the canonical regex / matcher / heuristic |
| `severity_tier` | One of `low` / `medium` / `high` / `critical` (canonical buckets: <40 / 40-69 / 70-89 / 90+) |
| `rationale` | Why this is a security risk — links to CVEs, threat-modeling write-ups, prior incidents |
| `false_positive_history` | Date-stamped log of FP reports + how they were resolved (kept; not redacted) |
| `limitations` | What the rule cannot catch. Mandatory — no rule ships without a limitations section |
| `version_history` | Per-version changelog (additive only; old behavior re-derivable from git) |

## Scoring is deterministic

- **Same input → same score**, byte-for-byte. The rubric version is part of the scan input.
- Every scan report records its `rubric_version` (semver) in the response payload.
- A vendor can verify a finding by running the exact `rubric_version` against the exact artifact bytes — the result is reproducible without platform participation.
- **No randomness, no ML-as-a-black-box.** Heuristics may use ML-trained classifiers, but the classifier weights ship versioned under `rubric/<category>/_models/` and the rule doc names which model version it uses.

## Rule-RFC workflow

New rules and rule changes go through a public RFC:

1. **Open issue** via `.github/ISSUE_TEMPLATE/03-rule-proposal.yml`. Title format: `RFC: SS-<CATEGORY>-<NAME>-NN — <short description>`.
2. **7-day comment window** — public can leave comments; maintainer labels with `rfc/discussion`.
3. **Maintainer decision** at end of window: `rfc/accepted` → proceed to PR; `rfc/rejected` → close with a substantive rationale in a final comment; `rfc/needs-changes` → extend the window once.
4. **Implementation PR** adds `rubric/<category>/<name>-NN.md` + the detector code under `services/api/app/scanner/<category>/` + tests. The PR description links the RFC issue.
5. **Activation** is gated on a passing CI run + at least one maintainer approval.

## Deprecation policy

Rules are **never silently retired**. A deprecation:

1. Opens an RFC labeled `rfc/deprecate`.
2. On acceptance, the rule's doc gains a `deprecated_in_version: <semver>` field and a `deprecation_rationale` section.
3. The detector keeps running for **one minor version** with `severity_tier: low` and a "deprecation pending" annotation on every finding.
4. The next minor version removes the detector code but keeps the rule doc forever — historical scans must remain explainable.

## Limitations — every rule

Every rule's `limitations` section names what it cannot catch. Examples:

- `SS-MCP-POISON-UNICODE-01.limitations`: "Cannot detect zero-width characters re-encoded as numeric entities (`&#8203;`); rule operates on decoded text only."
- `SS-HOOKS-RCE-01.limitations`: "Cannot detect obfuscated shell-RCE via runtime string concatenation; rule operates on static pattern match."

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
| New per-rule contract field | "Per-rule contract" table + every existing rubric doc backfilled in the same PR |
| Rule-RFC workflow change | "Rule-RFC workflow" + `.github/ISSUE_TEMPLATE/03-rule-proposal.yml` |
| Deprecation policy change | "Deprecation policy" + every rule mid-deprecation reviewed |
| Scoring determinism change (e.g. new ML model integration) | "Scoring is deterministic" — re-verify the same-input-same-score invariant |
