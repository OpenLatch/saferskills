---
title: "saferskills list"
description: "Show your full local capability inventory across detected agents, annotated with trust scores."
updated: 2026-06-16
---
`saferskills list` shows your full local inventory — every capability discovered across your detected agents, regardless of how it was installed — each annotated with its security score where known. It uses the same discovery the no-target [`capability`](/docs/install/cli-reference/scan/) audit performs, so it sees capabilities you added by hand, not just ones the CLI installed. On a terminal it then offers to scan the unscanned ones inline.

## How do I list installed capabilities?

Run the command with no arguments:

```bash
npx saferskills list
```

The CLI scans each detected agent's own config directories, collects every capability it finds, and renders one annotated row per capability. The eight supported agents and their config locations are covered in the [per-agent guides](/docs/install/per-agent-guides/claude-code/).

## What does each row show?

Each capability is annotated with its security score, and the source of that score depends on how the capability is tracked:

- **CLI-installed** capabilities show the **live current score** plus any drift since install — the same re-verification [`update`](/docs/install/cli-reference/update/) performs.
- **Previously scanned** capabilities (audited but not installed through the CLI) show a **cached score** and its age, read from `~/.saferskills/scan_cache.json`. Cache entries older than 90 days are dropped.
- Anything else shows `○ not scanned`.

On a TTY, `list` then offers to scan the unscanned capabilities inline and re-renders with the new scores. In headless mode — `--json`, `--quiet`, or `--non-interactive` — it prints a hint pointing at the [`capability`](/docs/install/cli-reference/scan/) audit instead of launching the interactive scan.

## What flags and exit codes apply?

The [global flags](/docs/install/global-flags/) apply. `--json` emits the inventory as machine-readable data on stdout and suppresses the inline-scan prompt; `--quiet` and `--non-interactive` do the same. Exit codes follow the shared convention — `0` on success, `4` if an agent config directory can't be read, `6` if a score lookup needs the API and it is unreachable.

## Where do I go next?

- [saferskills capability](/docs/install/cli-reference/scan/) runs the full audit that backs this inventory.
- [saferskills update](/docs/install/cli-reference/update/) re-verifies the scores of installed capabilities.
- [Managing your agents](/docs/concepts/managing-your-agents/) explains how the CLI discovers what is installed.
