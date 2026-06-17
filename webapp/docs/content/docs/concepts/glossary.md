---
title: "Glossary"
description: "Definitions for every SaferSkills term: skill, MCP server, hook, plugin, capability, sub-score, finding, color band, drift, prompt injection, and more."
updated: 2026-06-16
---
This page defines the terms used throughout the SaferSkills documentation. Each term has its own anchor, so other pages can link straight to it — for example `[prompt injection](/docs/concepts/glossary/#prompt-injection)`. Where a fuller treatment exists, the definition links to it.

## LLM

A large language model — the AI model an agent is built around, which interprets your prompts and the external content it reads, then decides what to do. SaferSkills statically scans the [capabilities](#capability) an LLM-based agent loads and behaviorally tests the running agent with an [Agent Scan](#agent-scan).

## Skill

A bundled [capability](#capability) — typically a `SKILL.md` file plus supporting assets — that extends an agent with functions, instructions, or workflows it loads and calls at runtime. The agent reads the skill body as trusted context, which is why the body is a security surface. See [Skills](/docs/concepts/skills/).

## MCP server

A process that exposes external tools to an agent over the Model Context Protocol (MCP), the open standard agents use to discover and call capabilities outside their own runtime. Because the agent trusts each tool's description, MCP servers are exposed to [tool poisoning](#tool-poisoning). See [MCP servers](/docs/concepts/mcp-servers/).

## Hook

A shell command an agent runs automatically when a lifecycle event fires (before a tool runs, after a file is written, on session start). A hook executes with the agent's privileges and no further confirmation, making it the highest-risk capability kind. See [Hooks](/docs/concepts/hooks/).

## Plugin

A package that bundles several capabilities — skills, MCP servers, hooks, and configuration — into one installable unit, combining each one's risk surface. See [Plugins](/docs/concepts/plugins/).

## Rules

An editor rule-file capability (for example `.cursorrules`, `.windsurfrules`, or `.cursor/rules/*.mdc`) that supplies standing instructions an editor agent applies to its work. Rules is one of the five detection categories and can carry the same injection and obfuscation risks as a skill body.

## Capability

The unit SaferSkills scans and catalogs: one skill, one MCP server, one hook, one plugin, or one rules set. One catalog entry equals one capability, and several capabilities can share a single GitHub repository — each is scored independently. See [Managing your agents](/docs/concepts/managing-your-agents/).

## Canonical ID

The stable per-capability identity SaferSkills assigns so the same capability resolves to the same catalog entry and `/items/<slug>` permalink across scans. It is what lets version history, badges, and the right-of-reply attach to one durable record rather than a moving target.

## Sub-score

One of the five 0–100 axes that combine into the aggregate: Security (35%), Supply Chain (20%), Maintenance (15%), Transparency (15%), and Community (15%). Each sub-score is `max(0, 100 − Σ penalties)`. See [How scoring works](/docs/concepts/how-scoring-works/).

## Aggregate score

The single 0–100 number for a capability: the rounded weighted sum of the five [sub-scores](#sub-score), then capped by the [severity ceiling](#severity-tier) when an active high or critical finding applies. It buckets into a [color band](#color-band). See [How scoring works](/docs/concepts/how-scoring-works/).

## Color band

The four-band bucketing of the [aggregate score](#aggregate-score): **Green ≥80** (Approved), **Yellow 60–79** (Watch), **Orange 40–59** (Caution), **Red 0–39** (Block). A band is a reading aid — a Red score means "review before use," not "do not use."

## Severity tier

The five-tier ladder a [finding](#finding) is rated on, each with a fixed penalty: `info` (0, advisory only) · `low` (5) · `medium` (12) · `high` (25) · `critical` (40). One active `critical` finding caps the whole [aggregate score](#aggregate-score) at ≤15; one active `high` caps it at ≤45.

## Finding

A single result from a scan: one [`rule_id`](#rule_id) that fired, its [severity tier](#severity-tier), the file path and line range, and a quotable line of evidence. Findings are never silently deleted — a verified appeal annotates them with the outcome. See [Finding evidence](/docs/security-and-methodology/finding-evidence/).

## rule_id

The stable identifier for a detection rule, in the grammar `SS-<CATEGORY>-<NAME>-NN` (for example `SS-HOOKS-RCE-CURL-PIPE-01`). Every finding names its `rule_id` so the verdict is traceable to a documented rule on the [live methodology page](/methodology). Behavioral [Agent Scan](#agent-scan) tests use a separate `AS-NN` grammar.

## Evidence / evidence_excerpt

The matched-line window shown on a finding so you see the exact bytes that triggered the rule. The `evidence_excerpt` is resolved at request time from the stored snapshot and lives only on the report — the persisted scan trace stores a hash of the matched content, never the raw payload. See [Finding evidence](/docs/security-and-methodology/finding-evidence/).

## Drift / rug-pull

A change in a capability's content between scans — detected as a content-hash difference. A "rug-pull" is the malicious case: a trusted capability ships a poisoned update after it has earned installs. SaferSkills' hash-drift rule (`SS-MCP-SUPPLY-CHAIN-HASH-DRIFT-01`) catches the change, though not the intent behind it.

## Prompt injection

Untrusted content that the model reads as instructions, causing it to act against the user's intent. Indirect prompt injection arrives via external content the model ingests — exactly what a skill body or an MCP tool description is. OWASP ranks it [LLM01:2025](https://genai.owasp.org/llmrisk/llm01-prompt-injection/), the top risk in the OWASP Top 10 for LLM Applications.

## Tool poisoning

An attack specific to [MCP servers](#mcp-server): malicious instructions hidden in a tool's description, invisible to the user but read by the model. Demonstrated by [Invariant Labs](https://invariantlabs.ai/blog/mcp-security-notification-tool-poisoning-attacks) (April 2025) and listed as MCP03:2025 in the [OWASP MCP Top 10](https://owasp.org/www-project-mcp-top-10/).

## Agent Scan

A behavioral assessment of a whole running agent — as opposed to a static component scan of files. It grades how an agent *behaves* against a pack of behavioral tests (`AS-01` … `AS-22`) run against mock tools only, with zero real side effects. See [Agent Scan](/docs/concepts/agent-scan/).

## Right-of-reply

The vendor appeal channel: a verified repository owner can publicly respond to a verdict, and a verified appeal triggers a re-scan with a one-hour response SLA. Findings are annotated with the appeal outcome, never silently removed. Uploads (no repo to verify) have no right-of-reply.

## Scan run

One scan of a repository, which discovers and scores every [capability](#capability) it contains and rolls them up into a repo report. Each run records its `ref_sha` (the scanned commit, or `content_hash_sha256` for an upload) so the verdict is reproducible.

## rubric_version

The git SHA of the `rubric/` rule set at the moment of a scan, stamped on every report alongside `engine_version`. Re-running the same `rubric_version` against the same bytes reproduces the verdict byte-for-byte, which is what makes SaferSkills deterministic and auditable. See [How scoring works](/docs/concepts/how-scoring-works/).
