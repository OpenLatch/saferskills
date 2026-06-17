---
title: "How Scoring Works"
description: "How SaferSkills turns a rubric of static rules into a deterministic, reproducible 0–100 score and a color band."
updated: 2026-06-16
author: "SaferSkills Team"
---
A SaferSkills score is the output of a fixed rubric, not an opinion. The scan runs a versioned set of detection rules over an artifact's bytes, sums each rule's severity penalty into five weighted sub-scores, and combines them into a single aggregate from 0 to 100 that maps to a color band. The same input always produces the same score — there is no model, no seed, no temperature in the verdict path.

## What does the score actually represent?

The score represents how an artifact measured against a published rubric at a specific version — nothing more. A high score means few rules fired; a low score means rules fired and carried penalties. It is **methodology, not endorsement**: SaferSkills publishes the rules, the math, and the evidence so you can decide, but it never tells you which capability to install. A low score reads as "review this before you use it," never "don't use it."

Every verdict is built from three layers, each documented and reproducible:

1. **The rubric** — a set of detection rules under [`rubric/`](https://github.com/OpenLatch/saferskills/tree/main/rubric), one Markdown-plus-YAML file per rule. Each rule has a stable `rule_id`, a severity, a sub-score it contributes to, and a maximum penalty `weight`.
2. **The aggregate** — five sub-scores, each `0–100`, combined by a fixed weighted sum and then clamped by a severity ceiling.
3. **The band** — the aggregate bucketed into Green, Yellow, Orange, or Red.

There is no human moderation queue between a finding and a score. If you disagree with a verdict you do not appeal to taste; you re-run the exact rules and check the math. See [the five sub-scores](/docs/security-and-methodology/5-sub-scores/) for the weighting detail and [detection categories](/docs/security-and-methodology/detection-categories/) for what each rule family looks for.

## How is an artifact discovered and scored?

A scan targets a repository, and one repository can hold several capabilities — a Skill, an MCP server, hooks, a Cursor rules set. SaferSkills walks the file tree, identifies each capability, and **scores each one independently** against the rules for its kind. Discovery is deterministic and static: the same file tree always yields the same capabilities, with no network call and no inference involved.

The repo report then shows every capability with its own score and findings, plus a consolidated repo score that is the rounded mean of those capability scores. One catalog entry equals one capability, so each capability links to its own permalink page with version history. A repository with no recognizable capability is scored as a single whole-repo entry, so every scan produces at least one score.

## How are penalties assigned to a finding?

Each finding carries a severity, and severity maps to a fixed per-finding penalty. The penalty is read from the rule's `weight` frontmatter field and is never tuned at runtime:

| Severity | Per-finding penalty |
|---|---|
| `info` | 0 (advisory only — surfaces in the trace, no score impact) |
| `low` | 5 |
| `medium` | 12 |
| `high` | 25 |
| `critical` | 40 |

`info` findings are first-class — they appear in the report and the scan trace — but they carry weight 0 and never move the score. They exist to surface context (for example, a low star count) without pretending that context is a security signal.

## How is each sub-score calculated?

Each of the five sub-scores starts at 100 and subtracts the penalties of every finding assigned to that sub-score:

```text
sub_score = max(0, 100 − Σ penalty_i)
```

The `max(0, …)` floor means a sub-score never goes negative. One additional rule applies at the sub-score level: if any finding contributing to a sub-score is `critical`, that sub-score is capped at **20** for breakdown coherence:

```text
if any contributing finding is critical:
    sub_score = min(sub_score, 20)
```

This per-sub-score cap exists so the breakdown reads honestly — a sub-score with a critical finding can never show a comfortable number — but, as the next section explains, the aggregate-level severity ceiling is what actually dominates a verdict.

## How is the aggregate built from the five sub-scores?

The aggregate is a fixed weighted sum of the five sub-scores, rounded to a whole number:

```text
aggregate = round(
    0.35 · security
  + 0.20 · supply_chain
  + 0.15 · maintenance
  + 0.15 · transparency
  + 0.15 · community
)
```

The weights are locked: **Security 35%, Supply Chain 20%, Maintenance 15%, Transparency 15%, Community 15%.** Security carries the largest single weight because the most consequential failures — prompt injection, dangerous shell, credential exfiltration — are security failures. See [the five sub-scores](/docs/security-and-methodology/5-sub-scores/) for exactly what each axis measures.

## Why doesn't a critical security flaw get diluted by good docs?

Because a severity ceiling clamps the whole aggregate, not just the security axis. With Security at only 35% of the weight, a critical security finding amid otherwise-clean axes would land near the low-70s — mathematically unable to drop into the "block" range from security problems alone, because 65% of the weight is non-security. A serious flaw would be diluted by good documentation and a healthy community.

The severity ceiling fixes this structurally. The worst **active** finding implies a hard cap on the whole aggregate:

- one active **critical** finding caps the aggregate at **≤15** (solidly Red);
- one active **high** finding caps the aggregate at **≤45**;
- `info` and shadow findings never trigger a ceiling.

```text
aggregate = min(weighted_aggregate, ceiling)   # when a ceiling applies
```

For a repository with multiple capabilities, the same ceiling is applied over the **union** of every capability's findings, so one dangerous capability among many clean ones cannot be averaged back up to a passing score. The ceiling is the structural guarantee that a security failure cannot be hidden behind the 65% non-security weight.

## What are the color bands?

The aggregate is bucketed into four bands, each with a catalog badge:

| Band | Range | Badge |
|---|---|---|
| Green | 80–100 | Approved |
| Yellow | 60–79 | Watch |
| Orange | 40–59 | Caution |
| Red | 0–39 | Block |

The bands are a reading aid, not a recommendation. "Approved" means the rubric found little to flag at this version; "Block" means rules fired with weight. The bands describe what was observed — they do not certify safety, and they never tell you what to install. The SaferSkills CLI uses the aggregate as an install gate (its default minimum is 90), but that is a configurable guardrail you control, not a verdict baked into the score.

## Why is the score deterministic and reproducible?

There is **no LLM in the verdict path.** No probabilistic scoring, no random seed, no temperature, no editorial moderation. Detection is a set of documented static triggers — regular-expression matches, file-presence checks, repository-metadata checks — applied to bytes. The same artifact at the same rubric version produces the same findings and the same number, byte-for-byte.

To make that reproducible offline, every scan report records three identifiers:

- `rubric_version` — the git SHA of the `rubric/` tree at scan time;
- `engine_version` — the git SHA of the scan engine;
- `ref_sha` — the commit SHA of the scanned artifact (or, for a direct upload, `content_hash_sha256`, the sha256 of the sorted `{path → sha256}` map of the uploaded files).

A vendor — or anyone — can re-derive a historical verdict by checking out `rubric_version` and `engine_version`, fetching the artifact at `ref_sha`, and re-running the scan. The result matches because nothing in the path is stochastic. This is the foundation of the [vendor right-of-reply](/docs/for-authors/disputing-findings/): a dispute is a reproducible argument about rules and math, not a request for a favorable opinion.

## How does the score stay current as rules change?

Scoring is change-gated. A repository whose HEAD commit is unchanged — verified with a free conditional request — and whose stored `rubric_version` and `engine_version` already match the current ones is not re-scanned; that would only produce the same number. A content change, or a new rubric or engine version, is what triggers fresh work.

When the rubric or engine version advances, the already-scanned corpus is **re-evaluated from the stored artifact bytes** rather than re-crawled from GitHub, so every published verdict stays consistent with the active methodology while respecting upstream rate limits. New rules do not jump straight into the score, either: they ship in a shadow state first, firing and recording findings at weight 0 until a false-positive audit promotes them. See [contribute a rule](/docs/security-and-methodology/contribute-a-rule/) for the full lifecycle.

## How does a finding turn into a number you can trust?

Each finding is engineered to be self-explanatory and reproducible from its trace alone. It carries the firing `rule_id`, the severity, a plain-English title, an explanation of why it matters, a remediation, and a matched-line excerpt drawn from the stored snapshot — while the persisted scan trace keeps only hashes and positions, never raw payload. That separation is what lets SaferSkills show you the exact line that triggered a finding without ever republishing a secret in the trace itself. The full mechanics are in [finding evidence](/docs/security-and-methodology/finding-evidence/).

For the complete, searchable rule list — every rule's severity, sub-score, trigger logic, framework mappings, and limitations, rendered live at the recorded `rubric_version` — see the [methodology page](/methodology) on the main site.

Prompt injection is the threat the security axis weights most heavily, and for good reason: OWASP ranks [prompt injection as LLM01:2025](https://genai.owasp.org/llmrisk/llm01-prompt-injection/), the top risk in the OWASP Top 10 for LLM Applications, for the second consecutive edition. A skill body or an MCP tool description is exactly the kind of untrusted external content an indirect injection rides in on — which is why the rubric devotes a whole family of rules to it.

**Author:** SaferSkills Team — methodology maintainers.
