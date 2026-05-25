# SaferSkills Methodology

> v0 — current as of W1 (2026-05-25). The substantive rule contents land via the rule-RFC process starting W2 (Track B). This document is the public-facing summary; the contributor-facing detail lives in `.claude/rules/methodology.md`.

## Inputs

SaferSkills ingests one of:
- A GitHub repository URL (`https://github.com/<owner>/<repo>` or sub-tree)
- A direct skill / MCP / hook artifact URL (resolves to a Git ref or release artifact)
- An `npx`-installable package name (Track C, W4+)

Every submission becomes a deterministic, content-hashed catalog entry. Two submissions of the same artifact deduplicate to the same `catalog_item` row.

## Detection categories

| Category | What it catches | Status W1 |
|---|---|---|
| **Identity** | Author signature, GitHub org age, prior items, signing keys | rule set lands W2 |
| **Integrity** | File-hash drift, unsigned commits, content vs claimed version | W2 |
| **Behavior** | Shell RCE, `curl|bash`, prompt injection, tool poisoning, MCP rug-pull, hooks that disable monitoring | W2-3 (the bulk of the rubric) |
| **Provenance** | Supply chain (dependencies, transitive risk), SBOM presence, build-reproducibility | W3 |

The W1 repo ships **zero detection rules in `rubric/`**. The 50+ rules referenced in the PRD are authored under the rule-RFC process from W2.

## Scoring model

```
aggregate_score = round(
  0.25 * identity_score      +
  0.25 * integrity_score     +
  0.30 * behavior_score      +
  0.20 * provenance_score
)

# Each sub-score is 0-100, computed from per-rule penalties:
sub_score = clamp(100 - Σ (rule.severity_penalty × rule.match_count), 0, 100)
```

Severity penalties per rule are fixed in the rule's RFC and never tuned at runtime. The aggregate is bucketed into a tier:

| Tier | Range | Catalog badge |
|---|---|---|
| Green | 80–100 | ✓ Approved |
| Yellow | 60–79 | ⚠ Watch |
| Orange | 40–59 | ⚠ Caution |
| Red | 0–39 | ✗ Block |

The CLI's default install gate is **block on Red** with `--threshold` to tighten or `--force` to bypass (the bypass is recorded in the install audit log, W5+).

## Reproducibility

**Same input → same score.** Every scan report records:
- `rubric_version` — git SHA of the `rubric/` tree at scan time
- `engine_version` — git SHA of the scan engine
- `inputs_hash` — content hash of the scanned artifact

A vendor can re-derive any historical verdict by checking out `rubric_version` + `engine_version` + the artifact at `inputs_hash`. There is **no model**, **no random seed**, **no temperature**. Deterministic.

## Limitations

The rubric explicitly does not catch:
- **Compromised authors** — a long-standing trusted author can ship a poisoned update; SaferSkills will detect *the change* (rug-pull rule), not the intent.
- **Behavior at scan time vs install time** — adversarial fetched content that varies per request will only be caught on the runtime side (OpenLatch Capability Control, not SaferSkills).
- **Logic bombs gated on date / runtime conditions** — static analysis can flag the gate but not its trigger.
- **Closed-source artifacts** — SaferSkills only scans public source. Closed-source skills get a "Provenance: unscoped" badge, not a score.

Every detection rule's RFC carries its own "What this rule cannot catch" section. There are no black-box findings — if a rule fires, the rule_id + the exact line of evidence is in the public report.

## Rule lifecycle

```
RFC (issue) → 7-day comment window → maintainer decision → PR adds rubric/<rule_id>.json
            ↓ if approved                                ↓
            ── deprecation RFC → 30-day notice → removal PR
```

Full contract: `.claude/rules/methodology.md`.

## Vendor right-of-reply

Every verdict is appealable. Verified vendors (a `.saferskills/verify.txt` token in the scanned repo, or response from a maintainer email matching the repo) get a substantive public response within 1 hour for an active appeal. The appeal becomes a permanent comment on the catalog item — transparency over erasure.

See `.github/ISSUE_TEMPLATE/04-vendor-appeal.yml` and `.claude/rules/vendor-appeals.md`.

## Methodology changelog

(W1) Document created. No rule revisions yet — first RFCs land W2.
