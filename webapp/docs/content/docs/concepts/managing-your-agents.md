---
title: "Managing Your Agents"
description: "Consolidate the skills, MCP servers, and hooks installed across all your agents under one verifiable, scannable view."
updated: 2026-06-16
---
Most developers run more than one agent — Claude Code here, Cursor there, a CLI agent for scripts — and each keeps its own skills, MCP servers, and hooks in its own directory. The `saferskills` CLI consolidates all of them under one view: `saferskills list` enumerates what is installed across every agent it detects, and `saferskills capability` (with no target) audits the whole installed inventory in one pass. Nothing is verified by trust; everything is scannable.

## Why do my agents need a single view?

Capabilities scatter by design. Claude Code loads skills from `~/.claude/skills/`, Cursor reads MCP servers from `~/.cursor/mcp.json`, Codex uses `~/.codex/skills/`, and five more agents each have their own paths. Without a consolidating tool you have no single place to answer the basic question: *what is installed, where, and is any of it risky?* A poisoned MCP server or an auto-executing hook does not announce itself — and the [Sonatype 2024 supply-chain report](https://www.sonatype.com/state-of-the-software-supply-chain/introduction) found a 156% year-over-year rise in malicious open-source packages, so the inventory is worth knowing.

## How do I list what is installed?

`saferskills list` enumerates the [capabilities](/docs/concepts/glossary/#capability) installed across the agents the CLI detects, in one table. It reports each item's kind ([skill](/docs/concepts/skills/), [MCP server](/docs/concepts/mcp-servers/), [hook](/docs/concepts/hooks/), [plugin](/docs/concepts/plugins/)) and the agent it belongs to, so you see your whole footprint without opening eight config files.

```bash
saferskills list
```

Add `--json` for machine-readable output on stdout (human text always goes to stderr). The full reference is on the [`list` command page](/docs/install/cli-reference/list/).

## How do I audit everything at once?

`saferskills capability` with no target runs a static scan of every installed capability the CLI can find — the same deterministic engine that scores a repo, pointed at your local installs. Each capability gets a 0–100 [aggregate score](/docs/concepts/glossary/#aggregate-score) and a [finding](/docs/concepts/glossary/#finding) list, so a risky item surfaces with its [`rule_id`](/docs/concepts/glossary/#rule_id) and evidence rather than a vague warning.

```bash
saferskills capability
```

Point `capability` at a specific path or URL to scan one artifact instead. See the [scan command page](/docs/install/cli-reference/scan/) (which documents the `capability` command) for targets and flags.

## How does this fit with installing and scanning?

The audit is the read side of the same loop that governs installs. When you install with `saferskills install <name>`, the CLI gates on the [aggregate score](/docs/concepts/glossary/#aggregate-score) — the default minimum is 90 (`SAFERSKILLS_MIN_SCORE`) — so a low-scoring capability is held back unless you choose otherwise. Auditing with `saferskills capability` then lets you re-check what is already installed against the current rubric.

## Related reading

- [`saferskills list`](/docs/install/cli-reference/list/) — enumerate installed capabilities.
- [Scan a capability (`capability`)](/docs/install/cli-reference/scan/) — static scan of a path, URL, or your whole local install.
- [Per-agent guides](/docs/install/per-agent-guides/claude-code/) — install paths and config for each of the eight supported agents.
- [Glossary](/docs/concepts/glossary/) — definitions for every term above.
