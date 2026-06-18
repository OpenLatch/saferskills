# SaferSkills Methodology

> The substantive rule corpus lands via the rule-RFC process; the first batch of 55 rules ships with this document. The contributor-facing detail lives in [`../.claude/rules/methodology.md`](../.claude/rules/methodology.md); both stay in sync per [`../.claude/rules/documentation-sync.md`](../.claude/rules/documentation-sync.md).

## Inputs

SaferSkills ingests one of:

- A GitHub repository URL (`https://github.com/<owner>/<repo>` or sub-tree)
- A direct skill / MCP / hook / plugin / rules artifact URL (resolves to a Git ref or release artifact)
- A **directly uploaded** artifact file or `.zip` — scanned public or **unlisted** (private share via an unguessable link)
- An `npx`-installable package name (planned)

Every submission becomes a deterministic, content-hashed catalog entry. An upload is a second front-end into the *same* engine — it produces the same per-capability file index and the same scoring path, never a different one.

## Capability discovery

A scan targets a **repository**, and one repo can hold several capabilities — a Skill, an MCP server, hooks, a Cursor rules set. SaferSkills walks the file tree, identifies each capability, and **scores each one independently** against the rules for its kind. The repo report shows:

- every capability discovered, each with its own security score and findings;
- the **consolidated repo score** — the mean of those capability scores;
- a button to open each capability in the public catalog.

One catalog entry = one capability, so a capability links straight to its own `/items/<slug>` page with version history and a permalink. A repo with no recognisable capability is scored as a single whole-repo entry. Discovery is deterministic and static — the same file tree always yields the same capabilities.

## Sub-score taxonomy & weights

The aggregate score is a closed-form weighted sum of five sub-scores:

| Sub-score | Weight | What it catches |
|---|---:|---|
| **Security** | 35% | Prompt injection, obfuscation, dangerous shell, credential exfiltration |
| **Supply Chain** | 20% | Typosquat, owner-transfer, hash drift, signing posture, transitive risk |
| **Maintenance** | 15% | Commit recency, commit frequency, issue response time, CI health |
| **Transparency** | 15% | LICENSE / SKILL.md / README / CHANGELOG / SECURITY.md presence |
| **Community** | 15% | Stars, contributors, cross-registry presence, fork health |

## Severity ladder

5-tier:

| Severity | Penalty range | Notes |
|---|---|---|
| `critical` | −30 to −40 | An active critical caps the **whole aggregate** at ≤15 (see Severity ceiling below) |
| `high` | −20 to −30 | An active high caps the **whole aggregate** at ≤45 |
| `medium` | −10 to −20 | |
| `low` | −5 to −10 | |
| `info` | 0 | Advisory only; surfaces in trace, no score impact |

## Scoring model

```
sub_score   = max(0, 100 - Σ penalty_i)
              # if any contributing finding has severity=critical, cap the
              # sub-score at 20:
              sub_score = min(sub_score, 20)

weighted    = round(
                0.35 * security
              + 0.20 * supply_chain
              + 0.15 * maintenance
              + 0.15 * transparency
              + 0.15 * community
              )

# Severity ceiling — the lowest cap implied by the worst ACTIVE finding:
#   any active critical → 15;  any active high → 45;  else none.
aggregate   = min(weighted, ceiling)   if a ceiling applies else weighted
```

Penalty per finding is set in the rule's frontmatter (`weight` field, 0–40) and never tuned at runtime.

**Severity ceiling.** Because security is only 35% of the weight, a critical security failure with everything else clean would otherwise land near ~72 ("yellow / Watch") — the 65% non-security weight mathematically floors the aggregate well above the "block" band, so a serious flaw is diluted by good docs/community. The severity ceiling fixes this structurally: a single **active** critical finding caps the **whole aggregate** at **≤15** (solidly red / Block), an **active** high caps it at **≤45**. `info` and `shadow` findings never trigger it. The repo rollup applies the same ceiling over the union of every capability's findings, so one dangerous capability among many clean ones cannot be averaged back up. This **supersedes** the earlier per-sub-score critical-floor model (which capped only the security sub-score at 40) and amends the pure weighted-sum; the per-sub-score critical floor is retained at 20 (down from 40) only for breakdown coherence — the aggregate ceiling now dominates.

**Every public scan report renders the explicit math**: per-finding penalty, running sub-score, critical-floor application, weighted aggregate, severity-ceiling application, tier-band mapping. The report's `score_breakdown` field carries the same numbers in machine-readable form (`aggregate_math.severity_ceiling`).

The aggregate is bucketed into a tier:

| Tier | Range | Catalog badge |
|---|---|---|
| Green | 80–100 | ✓ Approved |
| Yellow | 60–79 | ⚠ Watch |
| Orange | 40–59 | ⚠ Caution |
| Red | 0–39 | ✗ Block |

The CLI's default install gate is **block on Red** with `--threshold` to tighten or `--force` to bypass (the bypass is recorded in the install audit log, planned).

## Rule lifecycle — shadow then active

New rules ship in `status: shadow` for 7 days. The detector fires and records findings in the public scan trace, but the rule's weight is 0 during the shadow window — no score impact.

After 7 days, the FP-audit harness ([`tools/fp-audit/`](https://github.com/OpenLatch/saferskills/tree/main/tools/fp-audit)) gates promotion:

- FP rate <10% on the 100-item hand-labelled fixture → `status: active`
- FP rate ≥10% → `shadow_until` extended +7 days with maintainer review

This protects launch-week false-positive risk without delaying the detection signal.

## Rule format

Rules live at `rubric/<CATEGORY>/<NAME>-NN.md`. Each is Markdown + YAML frontmatter:

```yaml
---
rule_id: SS-<CATEGORY>-<NAME>-NN
severity: info | low | medium | high | critical
sub_score: security | supply_chain | maintenance | transparency | community
weight: 0..40
status: shadow | active | deprecated
shadow_until: 2026-01-18         # required iff status: shadow
applies_to: [skill, mcp, rules, hooks, plugin]   # subset
title: >-                        # plain-English headline (no rule_id)
  Fenced code block that tells the agent to run a shell command
categoryLabel: Prompt injection  # optional; falls back to the sub-score title
explanation: >-                  # "why it matters"; may use {match} {path} {line} {count}
  SKILL.md is read by the agent as trusted instructions ...
severityRationale: >-            # optional; one clause tying severity to outcome (omit for info)
  a successful injection runs attacker-supplied shell on your machine.
remediation:                     # actionable fix shown on every finding
  action: Remove the runnable block, or rewrite it as a non-executable example.
  steps:                         # optional ordered steps
    - "Delete the curl … | sh one-liner."
  saferPattern:                  # optional Avoid → Safer pattern pair
    before: "curl … | sh"
    after: "review the pinned script before running it"
trigger:
  type: regex_match | file_glob_present | file_glob_absent | commit_history_check | metadata_check | composite_and_or
  ...                          # primitive-specific params
limitations:
  - "Cannot detect ..."
frameworks:                      # optional; external AI-risk taxonomy refs
  - owasp-llm:llm01
  - mitre-atlas:AML.T0051
prior_art:
  - https://...
---
```

CATEGORY is one of `{MCP, SKILL, RULES, HOOKS, PLUGIN}`. The 6 primitive trigger types are a closed enum extended only by RFC. **Every rule MUST carry the explainable-finding fields** `title`, `explanation`, and `remediation` (and SHOULD carry `severityRationale` unless `info`-tier): they make each published finding self-explanatory — a plain-English title, why it matters, and how to fix it — instead of a bare `rule_id`. The schema (`schemas/rubric-rule.schema.json`) marks them required, so a rule missing them fails `pnpm run generate` (the `validate` CI lane). They flow through codegen into `webapp/src/generated/rules/content.ts`, which the report surfaces render alongside the matched-line excerpt.

**Framework references (`frameworks`, optional).** A rule may map to the external AI-risk taxonomies — OWASP LLM Top 10 (`owasp-llm:<id>`), MITRE ATLAS (`mitre-atlas:<id>`), and CWE (`cwe:<id>`) — via short codes that resolve through a central catalog into clickable badges on the methodology card and on every scan-report finding. Where no honest AI-framework mapping exists (most maintenance / transparency / community rules) the field is omitted. The codes are a closed set: an unknown code hard-fails `pnpm run generate`, and the badged-vs-unbadged split is locked by a generator assertion so a new rule can't silently ship unmapped.

## Reproducibility

**Same input → same score.** Every scan report records:

- `rubric_version` — git SHA of the `rubric/` tree at scan time
- `engine_version` — git SHA of the scan engine
- `ref_sha` — commit SHA of the scanned artifact

A vendor can re-derive any historical verdict by checking out `rubric_version` + `engine_version` + the artifact at `ref_sha` and re-running the scan offline. **No model. No random seed. No temperature. No LLM in the verdict path.** Deterministic, byte-for-byte.

For a **directly uploaded** artifact there is no Git `ref_sha`; the durable identity is `content_hash_sha256` (sha256 of the sorted `{path → sha256}` map of the uploaded files). Re-running the same `rubric_version` against the same bytes reproduces the verdict identically. Uploads have **no auto-rescan** — there is no upstream ref to poll for drift.

## Coverage — everything indexed gets scanned

The catalog's value is the scan, not the index. **Every public-github capability we index is automatically and durably scanned** — there is no popularity gate keeping rows unscored. Scanning is **change-gated**: a repo whose HEAD commit is unchanged (verified with a free conditional request) and whose stored `rubric_version`/`engine_version` already match the current ones is not re-scanned. A content change, or a new rubric/engine version, is what triggers a fresh scan.

When the rubric or engine version advances, the whole already-scanned corpus is **re-evaluated from the stored artifact bytes** — no GitHub re-crawl — so every published verdict stays consistent with the active methodology while respecting upstream rate limits.

## Agent Scan — the behavioral pack

Alongside the static **component** scan above, SaferSkills runs a behavioral **Agent Scan** — a pack of behavioral tests (`rubric/AGENT/`, ids `AS-01` … `AS-22`) that probe how an agent *behaves*, not just what its files contain. The pack is a separate taxonomy from the `SS-<CATEGORY>` component rules: each AS-NN test is a documented behavioral probe with its own frontmatter contract.

Each test maps to the external AI-risk taxonomies — OWASP LLM Top 10, MITRE ATLAS, NIST, and CWE — so a finding is anchored to a recognised threat, never an opaque opinion.

**The behavioral score reuses the exact same model as the component scan** — the same per-finding severity penalties (`info 0 / low 5 / medium 12 / high 25 / critical 40`), the same severity ceiling (`critical → 15`, `high → 45`), and the same green/yellow/orange/red band mapping. A practitioner reads an Agent Scan report identically to a component report: same severity pills, same bands, same math. The score is `100 − Σ penalties`, floored at 0, then capped by the worst-finding ceiling; the report carries the same per-finding signed-modifier "How the score moved" breakdown the component report uses.

Grading is **deterministic and has no LLM in the verdict path** — the cloud re-derives each per-run canary and decides vulnerable-or-not over the submitted evidence; identical evidence at the same pack version produces an identical verdict. The agent never self-grades (the submission carries no verdict field). A scan also reports a **confidence** (`high` / `medium` / `low`) driven by how many optional capabilities were present — a missing optional capability lowers *confidence*, **never the score** (the test is recorded `n_a`, not a penalty). An implausible evidence pattern (the per-run decoy surfaced but no real canary did) adds an advisory `tamper-suspected` label and floors confidence — but **never** changes the score.

Verdicts use **observation language, never assurance language**: a test reports "observed vulnerable" or "not observed under pack v<version>" — never "secure", "safe", or "certified". A clean run means the pack did not observe the behavior at that version, not a guarantee of safety.

## Scan-trace transparency

Every finding carries: `rule_id`, `severity`, `file_path`, `line_start`/`line_end`, `matched_content_sha256` (hash only — the raw matched content is never published per [`../.claude/rules/security.md`](../.claude/rules/security.md) § Scan-trace transparency), `remediation_link` to the rule source at the recorded `rubric_version`. The per-finding payload is capped at 4 KiB; the per-scan trace at 256 KiB.

## Agent compatibility (catalog metadata)

Each catalog item carries an `agent_compatibility` list — the agent platforms the artifact can run on. It is **catalog metadata, not a scoring input**: it never affects a score, only the catalog's *Agent compatibility* filter. Because it is metadata (not a verdict), it is derived by a documented deterministic mapping rather than the rule-RFC process.

Currently there is no per-artifact manifest parse, so the value is derived **deterministically from the artifact `kind`** (the canonical mapping, mirrored in `services/api/app/services/agent_compat.py::agent_compatibility_for` and the `0003_add_agent_compatibility` backfill — the `skill` set later widened by `0017_skill_compat_codex`, then to all eight agents by `0024_skill_compat_all_agents`):

| `kind` | `agent_compatibility` | Rationale |
|---|---|---|
| `mcp_server` | `claude-code, cursor, codex, copilot, windsurf, cline, gemini, openclaw` | MCP is a cross-agent transport standard — every supported agent can consume it |
| `skill` | `claude-code, cursor, codex, copilot, windsurf, cline, gemini, openclaw` | The Claude Skills (`SKILL.md`) format — the install CLI's general renderer deposits a native form for every supported agent: the `SKILL.md` verbatim for the skills-dir agents (Claude Code, OpenClaw, Codex, Copilot, Gemini), a rendered `.mdc`/rules file for the rules-dir editors (Cursor, Windsurf, Cline), and a shared `AGENTS.md`/`GEMINI.md` pointer block for Codex/Copilot/Gemini |
| `plugin` | `claude-code, openclaw` | Claude Code plugin packaging |
| `hook` | `claude-code, openclaw` | Claude Code lifecycle hooks |
| `rules` | `cursor, windsurf, cline, copilot` | Editor rule-file format consumed by those editors |

The agent id enum is closed (`schemas/catalog-item.schema.json::agentCompatibility`). Unknown kinds map to the empty list — no claim is the honest default.

**TODO (ingestion / methodology RFC):** refine the mapping with real manifest signals — declared `engines`/`agents` manifest fields, MCP transport detection, and editor-rule frontmatter — instead of kind alone. When the mapping changes, ship a fresh backfill migration so existing rows stay consistent.

## Limitations

The rubric explicitly does NOT catch:

- **Compromised authors** — a long-standing trusted author can ship a poisoned update; the rug-pull rule (hash-drift detector) catches the change, not the intent.
- **Behaviour at scan time vs install time** — adversarial fetched content that varies per request is a runtime concern (OpenLatch Capability Control, not SaferSkills).
- **Logic bombs gated on date / runtime conditions** — static analysis can flag the gate but not its trigger.
- **Closed-source artifacts** — SaferSkills only scans public source. Closed-source artifacts get a "Provenance: unscoped" badge, not a score.

Every detection rule's `limitations` frontmatter field names what it cannot catch — there are no black-box findings.

## Rule-RFC workflow

```
RFC (issue) → 7-day comment window → maintainer decision → PR adds rubric/<CATEGORY>/<NAME>-NN.md
            ↓ if approved                                ↓
            ── deprecation RFC → 30-day notice → removal PR
```

Deprecated rules stay in git history forever — historical scans must remain explainable.

Full governance contract: [`../.claude/rules/methodology.md`](../.claude/rules/methodology.md).

## Vendor right-of-reply

Every verdict is appealable. Verified vendors (a `.saferskills/verify.txt` token committed to the scanned repo, or maintainer email match) get a substantive public response within 1 hour for an active appeal. The appeal becomes a permanent comment on the catalog item — transparency over erasure.

See [`../.github/ISSUE_TEMPLATE/04-vendor-appeal.yml`](../.github/ISSUE_TEMPLATE/04-vendor-appeal.yml) and [`../.claude/rules/vendor-appeals.md`](../.claude/rules/vendor-appeals.md).

## Live methodology page

The auto-rendered rubric ships at [`https://saferskills.ai/methodology`](https://saferskills.ai/methodology) — every rule's frontmatter is surfaced as a RuleCard with its plain-English name + description, the severity pill (the same one used on scan-report findings), sub-score, status, OWASP / MITRE ATLAS / CWE framework badges, the raw trigger collapsed behind a "Detection logic" fold, limitations, and a permalink to the rule source at the current `rubric_version`. Search matches name, description, category, and framework refs; the toolbar exports the currently-visible rules to CSV (name as the first column).

## Methodology changelog

- **v1** — 5-axis sub-score taxonomy, 5-tier severity ladder, shadow/active lifecycle, critical-floor scoring. First-batch rubric (55 rules) lands. Public methodology page auto-renders from `rubric/`.
- **v0** — Placeholder 4-axis taxonomy (Identity / Integrity / Behavior / Provenance). Superseded by v1.
