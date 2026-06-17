---
title: "saferskills capability"
description: "Statically scan a Skill, MCP, hook, plugin, or rules artifact — or audit every capability installed across your agents."
updated: 2026-06-16
---
`saferskills capability [path|url]` statically scans a single artifact — a Skill, hook, MCP server, plugin, or rules file — by local path or GitHub URL, and prints its trust score and findings. With **no target**, it instead audits every capability installed across your detected agents in one run. Both paths run the same deterministic [scan engine](/docs/concepts/how-scoring-works/) the public catalog uses, with no LLM in the verdict path.

## How do I scan a single artifact?

Pass a local path or a GitHub URL:

```bash
npx saferskills capability ./my-skill
npx saferskills capability https://github.com/acme/devtools-agent-kit
```

The artifact is uploaded, scanned, and rendered as a per-capability report — the same five-axis breakdown and rule trace you get on `saferskills.ai`. The capability page documents what those findings mean in [read a scan report](/docs/find-and-verify/read-a-scan-report/).

## How do I audit everything I have installed?

Run it with no target:

```bash
npx saferskills capability
```

This discovers every capability installed across your detected agents — skills, MCP servers, hooks, rules, **slash commands, subagents, and installed plugins** — from each agent's own config (for example, Claude's `commands/`, `agents/`, and `plugins/cache/`; Codex's `prompts/`; Gemini's `commands/`). It bundles them into one upload, scans them in one run, and renders a single per-capability audit report. Slash commands and subagents are scored as Skills; each plugin's active version is decomposed into its nested capabilities.

The audit reads from your agents' config directories, **not** from the install registry, so you need no prior SaferSkills installs to audit your setup — it scans whatever is there, however it got there. Scored capabilities are cached to `~/.saferskills/scan_cache.json` (keyed by a content hash of their files, drift-aware) so [`list`](/docs/install/cli-reference/list/) can show a score for a capability that was scanned but never CLI-installed.

## What subflags does the audit accept?

| Flag | Effect |
|---|---|
| `--to <agent>` | Scope the no-target audit to named detected agents (repeatable). Conflicts with a positional target. |
| `--private` | Keep the run unlisted (reachable only by its share token, auto-expires after 90 days). |
| `--detailed` | Expand per-capability axis bars and inline findings in the rendered report. |

The [global flags](/docs/install/global-flags/) apply as well — `--json` emits the report as machine data on stdout, `--quiet` suppresses the human banner.

## Why does scanning a repo matter?

Skills, MCP tool descriptions, hook commands, and rules files are untrusted external content the model reads — exactly the surface for [indirect prompt injection](/docs/concepts/glossary/#prompt-injection), which OWASP ranks as the top LLM risk, [LLM01:2025](https://genai.owasp.org/llmrisk/llm01-prompt-injection/). An MCP tool description can hide instructions invisible to you but visible to the model — Invariant Labs' demonstrated [Tool Poisoning Attack](https://invariantlabs.ai/blog/mcp-security-notification-tool-poisoning-attacks) exfiltrated a user's `~/.cursor/mcp.json` and SSH keys this way. Scanning before you install is how you catch that statically.

## What exit codes can capability return?

| Code | Meaning |
|---|---|
| `0` | Scan completed; no blocking findings. |
| `1` | Findings blocked, or the scan submission / Proof-of-Work failed, or the target was missing or unreadable. |
| `2` | Usage error (bad flags). |
| `6` | The API was unreachable, rate-limited, or offline. |

## Where do I go next?

- [saferskills agent](/docs/install/cli-reference/scan-agent/) runs the **behavioral** Agent Scan against a running agent — a complement to this static scan.
- [Read a scan report](/docs/find-and-verify/read-a-scan-report/) explains the score, the bands, and the rule trace.
- [Detection categories](/docs/security-and-methodology/detection-categories/) lists the rules a component scan runs.
