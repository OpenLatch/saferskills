---
title: "Quickstart"
description: "Install a verified AI capability end to end in about five minutes — and read its trust score before it ever touches your machine."
updated: 2026-06-16
---
In about five minutes you can install a verified capability and read its independent trust score first. Use the `saferskills` CLI: run `info` to see a capability's score and findings, then `install` to write it to your detected agents. The install command re-checks the score at install time and gates on it — by default it confirms before installing anything below 90, so the safe path is the default path.

## What do you need first?

You need Node (to run `npx`) or a Rust toolchain (for `cargo install`). Nothing else — reads against the public API are unauthenticated, and the CLI ships as a single prebuilt native binary. Run a command with no permanent install:

```bash
npx saferskills info mcp-server-github
```

`npx` downloads and runs the prebuilt binary for your platform. To install the CLI permanently instead:

```bash
npm install -g saferskills      # via npm
cargo install saferskills       # via crates.io
```

The CLI calls `https://saferskills.ai` by default. Output discipline is strict: machine-readable JSON goes to stdout, and everything human (steps, warnings, the banner) goes to stderr — so the `--json` output of any command is always safe to pipe.

## Step 1 — Find a capability

Browse the catalog at [`saferskills.ai/catalog`](/catalog) on the web, or search from the terminal. The interactive finder opens an fzf-style terminal UI where you type to live-filter a ranked list, narrow by facets, and preview each row's score:

```bash
npx saferskills search          # interactive finder (alias: find)
npx saferskills search redis    # seed the finder with a query
```

On a non-interactive shell (or with `--json`) `search` prints the catalog envelope as JSON instead of launching the UI. Once you have a name, move on to checking its score.

## Step 2 — Read the score before you install

Always run `info` (alias `check`) first. It resolves a name to a catalog item and prints the aggregate score, the tier, the findings, and the URL of the full public report:

```bash
npx saferskills info mcp-server-github
```

Read the aggregate score against the four color bands: **Green (≥80, Approved)**, **Yellow (60–79, Watch)**, **Orange (40–59, Caution)**, and **Red (0–39, Block)**. Remember that a single active critical finding caps the whole aggregate at ≤15, so a red score usually means a serious security or supply-chain finding fired — open the report URL and read which rule it was. A low score is not "do not use"; it means review before use. For the full breakdown of what each sub-score measures, see [how scoring works](/docs/concepts/how-scoring-works/).

To capture the score programmatically, add `--json`:

```bash
npx saferskills info mcp-server-github --json
```

## Step 3 — Install with the score gate

`install` writes a Skill or MCP server to your detected agents. Before it writes anything it shows a digest — the global score plus the five-axis breakdown — and discloses exactly which agents it will write to. Then it gates on the aggregate score:

```bash
npx saferskills install mcp-server-github
```

The default minimum score is **90** (the `SAFERSKILLS_MIN_SCORE` setting, 0–100). An item at or above the minimum installs after you confirm the target agents. An item **below** the minimum warns and asks before proceeding. A **red-tier** item (score `< 40`) requires you to type the item name to continue — a deliberate speed bump.

To tighten or relax the gate, set the minimum for one run:

```bash
SAFERSKILLS_MIN_SCORE=80 npx saferskills install mcp-server-github
```

`--yes` confirms a below-threshold install non-interactively; only `--force` bypasses the red-tier type-the-name gate. Use `--force` sparingly and only after reading the report.

## Step 4 — Confirm what was installed

List your full local inventory — every capability discovered across your detected agents, each annotated with its score where known:

```bash
npx saferskills list
```

On a TTY, `list` offers to scan the unscanned items inline. To reverse exactly what an install wrote, or to refresh installed capabilities and re-verify their scores:

```bash
npx saferskills uninstall mcp-server-github   # reverse the install
npx saferskills update --all                  # refresh + re-verify all
```

If your registry and filesystem ever drift apart, `doctor` diagnoses it (and `doctor --fix` repairs what it safely can):

```bash
npx saferskills doctor
```

## How do you audit what you already have?

Run `capability` with no target to audit every capability already installed across your agents — skills, MCP servers, hooks, rules, slash commands, subagents, and installed plugins — bundled into one scan and rendered as a single audit report:

```bash
npx saferskills capability              # audit your whole setup
npx saferskills capability ./my-skill   # scan one local artifact
npx saferskills capability https://github.com/owner/repo   # scan a repo
```

This needs no prior SaferSkills installs — it reads whatever is in your agents' own config directories, regardless of how it got there.

## Which agents does this work with?

The CLI detects and writes to all eight supported agents, each at its own install path — for example Claude Code (`~/.claude/skills/`), Cursor (`~/.cursor/mcp.json`), Codex (`~/.codex/skills/`), Copilot (`~/.github/copilot/`), Windsurf, Cline, Gemini (`~/.gemini/config/`), and OpenClaw (`~/.openclaw/skills/`). The CLI installs Skills and MCP servers; hooks, plugins, and rules are shown for discovery and link to their reports. Per-agent details live in the [per-agent guides](/docs/install/per-agent-guides/claude-code/).

## Where do you go from here?

For the full prose walkthrough with the synced per-agent tabs, see [install a skill](/docs/install/install-a-skill/). For every command, flag, exit code, and environment variable, see the [CLI reference](/docs/install/cli-reference/). To understand the score you just read, continue to [core concepts](/docs/getting-started/core-concepts/) and [how scoring works](/docs/concepts/how-scoring-works/). Terms you do not recognize are defined in the [glossary](/docs/concepts/glossary/).
