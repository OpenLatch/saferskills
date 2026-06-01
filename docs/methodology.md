# SaferSkills Methodology

> v1 — Phase A (W2). The substantive rule corpus lands via the rule-RFC process; the first batch of 55 rules ships with this document. The contributor-facing detail lives in [`../.claude/rules/methodology.md`](../.claude/rules/methodology.md); both stay in sync per [`../.claude/rules/documentation-sync.md`](../.claude/rules/documentation-sync.md).

## Inputs

SaferSkills ingests one of:

- A GitHub repository URL (`https://github.com/<owner>/<repo>` or sub-tree)
- A direct skill / MCP / hook / plugin / rules artifact URL (resolves to a Git ref or release artifact)
- An `npx`-installable package name (Track C, W4+)

Every submission becomes a deterministic, content-hashed catalog entry.

## Capability discovery

A scan targets a **repository**, and one repo can hold several capabilities — a Skill, an MCP server, hooks, a Cursor rules set. SaferSkills walks the file tree, identifies each capability, and **scores each one independently** against the rules for its kind. The repo report shows:

- every capability discovered, each with its own security score and findings;
- the **consolidated repo score** — the mean of those capability scores;
- a button to open each capability in the public catalog.

One catalog entry = one capability, so a capability links straight to its own `/items/<slug>` page with version history and a permalink. A repo with no recognisable capability is scored as a single whole-repo entry. Discovery is deterministic and static — the same file tree always yields the same capabilities.

## Sub-score taxonomy & weights

The aggregate score is a closed-form weighted sum of five sub-scores (PRD §5.2, locked decision **D-01**):

| Sub-score | Weight | What it catches |
|---|---:|---|
| **Security** | 35% | Prompt injection, obfuscation, dangerous shell, credential exfiltration |
| **Supply Chain** | 20% | Typosquat, owner-transfer, hash drift, signing posture, transitive risk |
| **Maintenance** | 15% | Commit recency, commit frequency, issue response time, CI health |
| **Transparency** | 15% | LICENSE / SKILL.md / README / CHANGELOG / SECURITY.md presence |
| **Community** | 15% | Stars, contributors, cross-registry presence, fork health |

## Severity ladder

5-tier per locked decision **D-02**:

| Severity | Penalty range | Notes |
|---|---|---|
| `critical` | −30 to −40 | Triggers critical-floor cap (see below) |
| `high` | −20 to −30 | |
| `medium` | −10 to −20 | |
| `low` | −5 to −10 | |
| `info` | 0 | Advisory only; surfaces in trace, no score impact |

## Scoring model

```
sub_score   = max(0, 100 - Σ penalty_i)
              # Critical floor: if any contributing finding has severity=critical,
              # cap the sub-score at 40:
              sub_score = min(sub_score, 40)

aggregate   = round(
                0.35 * security
              + 0.20 * supply_chain
              + 0.15 * maintenance
              + 0.15 * transparency
              + 0.15 * community
              )
```

Penalty per finding is set in the rule's frontmatter (`weight` field, 0–40) and never tuned at runtime. The critical floor (locked decision **D-13**) prevents one catastrophic finding from being averaged away by many minor passes — a `critical` security finding caps the security sub-score at 40 regardless of how many `info`-severity passes accompany it.

**Every public scan report renders the explicit math**: per-finding penalty, running sub-score, critical-floor application, weighted aggregate, tier-band mapping. The report's `score_breakdown` field carries the same numbers in machine-readable form.

The aggregate is bucketed into a tier:

| Tier | Range | Catalog badge |
|---|---|---|
| Green | 80–100 | ✓ Approved |
| Yellow | 60–79 | ⚠ Watch |
| Orange | 40–59 | ⚠ Caution |
| Red | 0–39 | ✗ Block |

The CLI's default install gate is **block on Red** with `--threshold` to tighten or `--force` to bypass (the bypass is recorded in the install audit log, W5+).

## Rule lifecycle — shadow then active

New rules ship in `status: shadow` for 7 days (locked decision **D-14**). The detector fires and records findings in the public scan trace, but the rule's weight is 0 during the shadow window — no score impact.

After 7 days, the FP-audit harness ([`tools/fp-audit/`](https://github.com/OpenLatch/saferskills/tree/main/tools/fp-audit)) gates promotion:

- FP rate <10% on the 100-item hand-labelled fixture → `status: active`
- FP rate ≥10% → `shadow_until` extended +7 days with maintainer review

This protects launch-week false-positive risk without delaying the detection signal.

## Rule format

Rules live at `rubric/<CATEGORY>/<NAME>-NN.md` (locked decision **D-04**). Each is Markdown + YAML frontmatter:

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

CATEGORY is one of `{MCP, SKILL, RULES, HOOKS, PLUGIN}`. The 6 primitive trigger types are a closed enum extended only by RFC.

## Reproducibility

**Same input → same score.** Every scan report records:

- `rubric_version` — git SHA of the `rubric/` tree at scan time
- `engine_version` — git SHA of the scan engine
- `ref_sha` — commit SHA of the scanned artifact

A vendor can re-derive any historical verdict by checking out `rubric_version` + `engine_version` + the artifact at `ref_sha` and re-running the scan offline. **No model. No random seed. No temperature. No LLM in the verdict path.** Deterministic, byte-for-byte.

## Scan-trace transparency

Every finding carries: `rule_id`, `severity`, `file_path`, `line_start`/`line_end`, `matched_content_sha256` (hash only — the raw matched content is never published per [`../.claude/rules/security.md`](../.claude/rules/security.md) § Scan-trace transparency), `remediation_link` to the rule source at the recorded `rubric_version`. The per-finding payload is capped at 4 KiB; the per-scan trace at 256 KiB.

## Agent compatibility (catalog metadata)

Each catalog item carries an `agent_compatibility` list — the agent platforms the artifact can run on. It is **catalog metadata, not a scoring input**: it never affects a score, only the catalog's *Agent compatibility* filter. Because it is metadata (not a verdict), it is derived by a documented deterministic mapping rather than the rule-RFC process.

At W2 there is no per-artifact manifest parse, so the value is derived **deterministically from the artifact `kind`** (the canonical mapping, mirrored in `services/api/app/services/agent_compat.py::agent_compatibility_for` and the `0003_add_agent_compatibility` backfill):

| `kind` | `agent_compatibility` | Rationale |
|---|---|---|
| `mcp_server` | `claude-code, cursor, codex, copilot, windsurf, cline, gemini, openclaw` | MCP is a cross-agent transport standard — every supported agent can consume it |
| `skill` | `claude-code, openclaw` | Claude Skills format; OpenClaw is Claude-compatible |
| `plugin` | `claude-code, openclaw` | Claude Code plugin packaging |
| `hook` | `claude-code, openclaw` | Claude Code lifecycle hooks |
| `rules` | `cursor, windsurf, cline, copilot` | Editor rule-file format consumed by those editors |

The agent id enum is closed (`schemas/catalog-item.schema.json::agentCompatibility`). Unknown kinds map to the empty list — no claim is the honest default.

**TODO (I-04 ingestion / methodology RFC):** refine the mapping with real manifest signals — declared `engines`/`agents` manifest fields, MCP transport detection, and editor-rule frontmatter — instead of kind alone. When the mapping changes, ship a fresh backfill migration so existing rows stay consistent.

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

The auto-rendered rubric ships at [`https://saferskills.ai/methodology`](https://saferskills.ai/methodology) — every rule's frontmatter is surfaced as a RuleCard with severity, sub-score, status, trigger summary, limitations, and a permalink to the rule source at the current `rubric_version`.

## Methodology changelog

- **v1 (Phase A, W2)** — Locked PRD-aligned 5-axis sub-score taxonomy, 5-tier severity ladder, shadow/active lifecycle, critical-floor scoring. First-batch rubric (55 rules) lands. Public methodology page auto-renders from `rubric/`.
- **v0 (W1)** — Placeholder 4-axis taxonomy (Identity / Integrity / Behavior / Provenance). Superseded by v1.
