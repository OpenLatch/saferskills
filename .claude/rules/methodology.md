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
| `title` | yes | Plain-English headline for the finding (NO rule_id) — a human sentence fragment naming what was found. Renders as the `.fc-title` on every report |
| `explanation` | yes | The "why it matters" paragraph (1–2 plain, second-person sentences: the risk + attack/outcome class). May use the closed placeholder set `{match}` `{path}` `{line}` `{count}` (filled at render from backend evidence; dropped gracefully when empty) + inline `<code>…</code>` |
| `severityRationale` | no | One clause tying severity to outcome ("HIGH — …"). Omit for `info`-tier |
| `categoryLabel` | no | Human category label for the meta line (e.g. "Prompt injection"). Falls back to the sub_score title |
| `remediation` | yes | Object `{ action (req), steps?: string[], saferPattern?: { before, after } }`. `action` is an imperative one-liner naming the user's construct; `saferPattern` is an Avoid→Safer **pattern** (never a product — anti-recommendation). `info`-tier → action "No action required — context only." |
| `limitations` | yes | What the rule cannot catch. **Mandatory** — no rule ships without limitations. Non-empty list |
| `frameworks` | no | Array of external AI-risk taxonomy codes (`owasp-llm:<id>` / `mitre-atlas:<id>` / `cwe:<id>`, e.g. `owasp-llm:llm01`, `mitre-atlas:AML.T0051`, `cwe:78`). Resolved by the central `FRAMEWORK_CATALOG` in `generate-methodology.cjs` into `{family,id,label,url}` badges on the methodology card + scan-report findings (an unknown code hard-fails the generator). Omit where no honest AI-framework mapping exists (most maintenance/transparency/community rules). The badged-vs-unbadged split is locked by a generator assertion (`EXPECTED_BADGED`/`EXPECTED_UNBADGED`, mirrored by `webapp/test/lib/rules-table.test.ts`) so a new rule can't silently ship unmapped |
| `prior_art` | yes | Array of URLs to CVEs, research papers, OWASP entries, vendor write-ups that motivate the rule |

The explainable-finding fields (`title` / `explanation` / `severityRationale` / `categoryLabel` / `remediation`) flow through `generate-methodology.cjs` into `webapp/src/generated/rules/content.ts` (the `RULE_CONTENT` map). The optional `frameworks` codes are resolved (via `FRAMEWORK_CATALOG`) and emitted alongside them in `content.ts` (consumed by the web `FindingDetail` badges) and in `webapp/src/generated/methodology/rules-table.ts` (the full per-rule table backing the methodology CSV export). The report surfaces compose the shared `FindingDetail` card (the v3 `.find-card`) from that map + the backend's per-finding `evidence_excerpt`. **The excerpt (the matched-line window shown in the card) is snapshot-sourced and lives ONLY on the report DTO — it is NOT a scan-trace field; the trace stays hash-only** (see `security.md` § Scan-trace transparency). New / changed rules ship `title` + `explanation` + `remediation` (+ `severityRationale` unless `info`); the schema marks them required so a rule missing them fails `pnpm run generate`.

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
- **Upload provenance (I-3.5).** A directly **uploaded** artifact is scanned by the *same* deterministic engine — upload is a second front-end producing the same per-capability file index, not a different scoring path. There is no `ref_sha` (no Git ref); the durable identity is `content_hash_sha256` = sha256 of the sorted `{path → sha256}` map of the uploaded files. Reproducibility is by re-running the same `rubric_version` against the same bytes (`content_hash_sha256` pins them). Uploads have **no auto-rescan** (there is no upstream ref to poll for drift).
- **No LLM in the verdict path.** No probabilistic scoring. No editorial moderation queue. Hard, structural.
- **No randomness, no ML-as-a-black-box.** Heuristics may use ML-trained classifiers, but the classifier weights ship versioned under `rubric/<CATEGORY>/_models/` and the rule doc names which model version it uses.

## Coverage — every indexed public-github capability is scanned

The catalog's value is the scan, not the index. **Indexing a public-github capability automatically + durably leads to it being scanned** — there is no popularity gate. A reconciliation drainer continuously selects public-github `quality_tier IN ('high','medium')` not-archived repos that are unscanned, stale-version, or stale-freshness (popularity-first, rate-limited) and enqueues a durable scan job; the ingestion merger also enqueues a scan on a new item or a content-hash change (`.claude/rules/ingestion.md` § Durable auto-scan pipeline).

- **Change-gated + content-addressed.** A repo whose HEAD ref is unchanged (a free conditional 304) and whose stored `rubric_version`/`engine_version` match the current ones is **not** re-scanned — only a content change or a version bump triggers work. The scan idempotency key is `(github_url, ref_sha, rubric_version)`, so an unchanged repo at unchanged rules is a cache no-op.
- **Rule/engine version bumps re-evaluate the corpus from stored bytes.** When `rubric_version` (or the engine) advances, every already-scanned capability is marked stale and a popularity-ordered drainer re-scores it **from the stored `artifact_blobs` snapshot** — no GitHub re-crawl. Such re-evals are recorded with `source='rescan_rules'`. This keeps the whole corpus consistent with the active rubric while respecting the GitHub budget.

## Capability discovery (per-capability scans)

A scan targets a **GitHub repo**, and one repo can host several capabilities (a Skill, an MCP server, hooks, …). The engine discovers each capability, scores it independently against its kind-scoped rules, and persists one catalog item + one `scans` row per capability — all grouped under one `scan_runs` row (the repo scan). The repo report (`/scans/<run_id>`) is a rollup over them.

- **Discovery is deterministic + static** (`app/scan/discovery.py`, pure over the file tree, no network). Signals per kind: a dir with `SKILL.md` (skill); `mcp.json`/`.mcp.json` or `package.json` with `mcpServers` (mcp_server); each `hooks/*.json` or a `.claude/settings.json` hooks block (hook); `plugin.json` / `.claude-plugin/` (plugin); `.cursorrules` / `.cursor/rules/*.mdc` / `.windsurfrules` (rules).
- **Kind-scoped scoring.** Each capability runs only its kind's rules (`rubric.by_kind`, matched on each rule's `appliesTo`). An embedded hook is HOOKS-scored only when discovered as its own capability.
- **Repo-wide files join every capability.** Root `LICENSE` / `README` / `SECURITY.md` / `CHANGELOG` / `.github/**` are unioned into every capability's file subset so the maintenance/transparency rules still fire per capability. Deepest path claims a file on overlap.
- **Repo aggregate = rounded mean** of the per-capability aggregate scores; a by-kind tally accompanies it. `tier_for(score)` is the single source for the band thresholds.
- **Zero-capability fallback (mandatory).** A repo with no capability signal yields exactly one synthetic whole-repo capability (kind inferred, default `skill`) → today's 1:1 behaviour is preserved; every scan has ≥1 capability.
- **Removed capabilities on a rescan are not deleted** (archived-public policy) — their items/scans persist. Snapshots/manifests are captured **per-capability subtree**.

See `.claude/rules/database.md` § Per-capability scans for the `scan_runs` storage contract.

## Sub-scores and aggregate (locked D-01 / D-02; D-13 superseded by the severity ceiling)

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
| `critical` | −30 to −40 | An active critical caps the **whole aggregate** at ≤15 (severity ceiling below) |
| `high` | −20 to −30 | An active high caps the **whole aggregate** at ≤45 |
| `medium` | −10 to −20 | |
| `low` | −5 to −10 | |
| `info` | 0 | Advisory-only; surfaces in trace, no score impact |

`sub_score = max(0, 100 − Σ penalty_i)`. If any finding in a sub-score has `severity: critical`, the sub-score is capped: `sub_score = min(sub_score, 20)`. `weighted = round(Σ sub_score × weight)`.

**Severity ceiling (supersedes D-13, amends D-01).** A weighted-sum aggregate dilutes a security failure — with security at only 35% weight, a critical security finding amid otherwise-clean axes lands ~72 ("yellow / Watch"), mathematically unable to drop below ~65 from security problems alone. The ceiling fixes this at the aggregate: `_severity_ceiling(findings)` returns the lowest cap implied by the worst **active** finding — `critical → 15`, `high → 45`, else `None` — and `aggregate = min(weighted, ceiling)` when a ceiling applies. `info` and `shadow` findings never trigger it (shadow stays weight-0 / no score impact). The repo rollup (`_score_file_index`) applies the **same** ceiling over the **union** of every capability's findings, so one dangerous capability can't be averaged back up by clean ones. This **supersedes** the per-sub-score critical-floor (D-13, formerly cap-security-sub-score-at-40); that per-sub-score floor is retained only at **20** (down from 40) for breakdown coherence — the aggregate ceiling dominates. Tier bands (`tier_for`) are unchanged. All scoring lives in the single chokepoint `app/scan/engine.py`; **future scans only** — there is no catalog-wide backfill (existing scans keep their scores until content changes or a re-scan, since `engine_version` stays `"unknown"` and the reconcile drainer only re-evaluates on a version mismatch).

Every public scan report renders the **explicit breakdown**: per-finding penalty, running sub-score, critical-floor application, weighted aggregate, severity-ceiling application, tier-band mapping. See the `score_breakdown` block in `schemas/scan-report.schema.json` (`aggregate_math.severity_ceiling`: `{ceiling, weighted_aggregate, applied}`).

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
7. **Every rule ships explainable-finding content** — `title` + `explanation` + `remediation` (+ `severityRationale` unless `info`). Enforced structurally by `schemas/rubric-rule.schema.json` (required) + the `validate` drift gate. The RFC (`03-rule-proposal.yml`) must include the proposed title/explanation/remediation.

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
