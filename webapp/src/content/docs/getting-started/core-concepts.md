---
title: "Core Concepts"
description: "A one-screen map of the five capability kinds, the 0–100 scoring model, and the trust model that ties SaferSkills together."
updated: 2026-06-16
---
SaferSkills rests on three ideas. First, the unit of analysis is a **capability** — a skill, MCP server, hook, plugin, or rules file. Second, every capability gets a **0–100 score** from five weighted sub-scores, bucketed into four color bands. Third, the **trust model** combines a static component scan, a behavioral Agent Scan, and a structural vendor right-of-reply. This page maps all three in one screen.

## What are the five capability kinds?

A capability is one indexable, scorable AI extension. There are five kinds, and one repository can hold several — each is discovered and scored independently.

- **[Skill](/docs/concepts/skills/)** — the `SKILL.md` instruction format; text the agent loads as trusted instructions. Fully scanned today.
- **[MCP server](/docs/concepts/mcp-servers/)** — a Model Context Protocol tool server the agent talks to; its tool *descriptions* are a key attack surface. Fully scanned today.
- **[Hook](/docs/concepts/hooks/)** — a lifecycle shell script that fires on agent events.
- **[Plugin](/docs/concepts/plugins/)** — a packaged bundle that can decompose into nested capabilities.
- **Rules** — an editor rule file (for example a Cursor `.mdc`) the editor applies to model behavior.

Skills and MCP servers are fully scanned in v1; the hooks, plugins, and rules categories exist in the rubric and are scored where coverage applies. Each capability links to its own `/items/<slug>` report. See the [glossary](/docs/concepts/glossary/) for precise definitions of every term used here.

## How is a capability scored?

The aggregate score runs 0–100 and is a weighted sum of five sub-scores:

| Sub-score | Weight | What it catches |
|---|---:|---|
| **Security** | 35% | Prompt injection, obfuscation, dangerous shell, credential exfiltration |
| **Supply Chain** | 20% | Typosquat, owner-transfer, hash-drift (rug-pull), unsigned releases |
| **Maintenance** | 15% | Commit recency, commit frequency, issue-response time, CI health |
| **Transparency** | 15% | LICENSE / README / CHANGELOG / SECURITY.md / manifest presence |
| **Community** | 15% | Stars, contributors, cross-registry presence, fork health |

Each sub-score starts at 100 and loses per-finding penalties: `info 0 · low 5 · medium 12 · high 25 · critical 40`. A sub-score is `max(0, 100 − Σ penalties)`, and a sub-score with any critical finding caps at ≤20. The aggregate is `round(0.35·security + 0.20·supply + 0.15·maintenance + 0.15·transparency + 0.15·community)`. The deeper math lives in [how scoring works](/docs/concepts/how-scoring-works/) and the [five sub-scores](/docs/security-and-methodology/5-sub-scores/) page.

## What do the score bands mean?

The aggregate maps to four color bands: **Green (≥80, Approved)**, **Yellow (60–79, Watch)**, **Orange (40–59, Caution)**, and **Red (0–39, Block)**. Severity tiers run `info` (advisory, zero weight), `low`, `medium`, `high`, and `critical`. The bands are advisory, not instructions — a low band means review before use, in keeping with the methodology-over-opinion stance.

## Why can a single finding dominate the score?

Because security must not be diluted by the 65% non-security weight. A severity ceiling caps the **whole aggregate** by the worst active finding: one active **critical** caps the aggregate at **≤15**, and one active **high** caps it at **≤45**. So a capability with a critical credential-exfiltration finding lands solidly red even if its docs, stars, and maintenance are pristine. This structural ceiling is what makes a serious flaw unmissable; see [how scoring works](/docs/concepts/how-scoring-works/) for the exact rule.

## What makes a score trustworthy?

Determinism. Scoring is closed-form with **no LLM in the verdict path** — no model, no seed, no temperature. Every scan stamps `rubric_version`, `engine_version`, and `ref_sha` (or `content_hash_sha256` for an upload), so a vendor can re-derive any verdict offline. Every finding carries a `rule_id` and a quotable line of evidence, and the persisted scan trace stores hashes and positions only, never raw payload. The same input always produces the same score.

## What is the trust model?

The trust model has three parts that reinforce each other:

- **Static component scan** — analyzes a capability's files without running them, against the documented [detection categories](/docs/security-and-methodology/detection-categories/).
- **[Agent Scan](/docs/concepts/agent-scan/)** — grades a *running* agent behaviorally against a pack of adversarial tests, using mock tools only (zero real side effects), with the identical scoring model. Verdicts use observation language ("observed vulnerable" / "not observed under pack v<version>"), never "secure" or "certified."
- **Vendor right-of-reply** — every verdict is appealable. A verified vendor gets a substantive public response within one hour, and findings are annotated with the appeal outcome, never silently deleted. The process is documented in [disputing findings](/docs/for-authors/disputing-findings/).

## Where do you go from here?

For each capability kind in depth, read the [skills](/docs/concepts/skills/), [MCP servers](/docs/concepts/mcp-servers/), [hooks](/docs/concepts/hooks/), and [plugins](/docs/concepts/plugins/) pages. For the scoring model, continue to [how scoring works](/docs/concepts/how-scoring-works/); for the behavioral side, see the [Agent Scan overview](/docs/concepts/agent-scan/). Every term on this page is defined in the [glossary](/docs/concepts/glossary/).
