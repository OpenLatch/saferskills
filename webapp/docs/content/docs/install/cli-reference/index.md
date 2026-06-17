---
title: "CLI Reference"
description: "Every saferskills command — info, install, update, scan, agent — with its flags and exit codes."
updated: 2026-06-16
---
The `saferskills` CLI installs and scans AI capabilities from your terminal against a verified trust score. It is a thin, fail-open client of the public SaferSkills API: reads are unauthenticated and uncapped, and the safe path is the easy path. Run any command with `npx saferskills <command>`, no permanent install required. This page lists every command and points to flags and exit codes.

## How do I run the CLI?

Run a command without installing anything using `npx`, which fetches the prebuilt native binary:

```bash
npx saferskills info mcp-server-github
npx saferskills install mcp-server-github
```

Or install it permanently with npm or Cargo:

```bash
npm install -g saferskills      # npm
cargo install saferskills       # crates.io
```

State lives under `~/.saferskills/` (override with `SAFERSKILLS_DIR`): `config.toml` holds `api_url`, `min_score`, and `telemetry`; `installs.json` is the install registry; `scan_cache.json` caches local scan results. The API origin resolves as `SAFERSKILLS_API_URL` → `config.toml` `api_url` → `https://saferskills.ai`.

## What commands does the CLI have?

| Command | Purpose |
|---|---|
| `info <name>` (alias `check`) | Resolve a name to a catalog item and print its score, tier, findings, and report URL. |
| [`install <name>`](/docs/install/cli-reference/install/) | Install a Skill or MCP server to your detected agents, gated on the aggregate score. |
| [`uninstall <name>`](/docs/install/cli-reference/uninstall/) | Reverse exactly what an install wrote. |
| [`update [--all]`](/docs/install/cli-reference/update/) | Refresh installed capabilities and re-verify their scores. |
| [`list`](/docs/install/cli-reference/list/) | Show your full local inventory across detected agents, annotated with scores. |
| `search [query]` (alias `find`) | Open an interactive catalog finder and installer; headless mode emits the catalog as JSON. |
| [`capability [path\|url]`](/docs/install/cli-reference/scan/) | Statically scan one artifact, or audit every capability installed across your agents. |
| [`agent`](/docs/install/cli-reference/scan-agent/) | Run a behavioral [Agent Scan](/docs/concepts/agent-scan/) against your running agents. |
| `doctor [--fix]` | Diagnose registry-versus-filesystem drift across detected agents. See [doctor](/docs/install/cli-reference/doctor/). |
| `completion <shell>` | Print a shell completion script for `bash`, `zsh`, `fish`, or PowerShell. |

The `info` and `check` aliases are interchangeable, as are `search` and `find`. The two pages under this section that document scanning use the real command names in their prose: the [scan page](/docs/install/cli-reference/scan/) documents `capability`, and the [agent scan page](/docs/install/cli-reference/scan-agent/) documents `agent`.

## What flags and exit codes apply?

Every command shares a set of global flags — `--json`, `--color`, `-v/--verbose`, `-q/--quiet`, `--yes`, `--force`, and `--non-interactive` (alias `--no-input`) — and a common output discipline: stdout is machine data, stderr is everything human. See [global flags](/docs/install/global-flags/) for the full table and the environment variables (`SAFERSKILLS_API_URL`, `SAFERSKILLS_MIN_SCORE`, `SAFERSKILLS_DIR`, telemetry controls).

Commands return a stable exit code so you can wire them into scripts and CI:

| Code | Meaning |
|---|---|
| `0` | OK |
| `1` | Generic error / findings block |
| `2` | Usage error (bad flags) |
| `3` | Item not found |
| `4` | Permission denied |
| `5` | Conflict (e.g. an already-installed item) |
| `6` | Network, rate-limit, or offline |
| `130` | Interrupted (SIGINT / Ctrl-C) |

## Where do I go next?

- [Install a skill](/docs/install/install-a-skill/) walks the install flow with the synced per-agent tabs.
- [Per-agent guides](/docs/install/per-agent-guides/claude-code/) cover the eight supported agents and their config paths.
- [How scoring works](/docs/concepts/how-scoring-works/) explains the score the install gate checks.
- [Read a scan report](/docs/find-and-verify/read-a-scan-report/) explains what `info` and `capability` print.
