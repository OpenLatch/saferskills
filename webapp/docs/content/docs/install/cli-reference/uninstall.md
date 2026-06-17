---
title: "saferskills uninstall"
description: "Remove a previously installed capability by reversing exactly what saferskills install wrote."
updated: 2026-06-16
---
`saferskills uninstall <name>` reverses exactly what an install wrote. It reads the install registry at `~/.saferskills/installs.json` to find every agent and config file the original install touched, then removes those entries — and only those entries — leaving anything you configured by hand untouched. Use it to cleanly back out a Skill or MCP server you installed through the CLI.

## How do I uninstall a capability?

Pass the same name you installed:

```bash
npx saferskills uninstall mcp-server-github
```

The CLI looks up the capability in `installs.json`, identifies which detected agents hold it, and removes the records the install added. Because uninstall replays the registry rather than guessing, it undoes a multi-agent install in one command — every agent the capability was written to is cleaned up together.

## What exactly does it remove?

Only what `saferskills install` recorded. The install registry tracks each file and config entry written per agent, so uninstall:

- removes the capability's entries from every agent that the install targeted,
- leaves manually added config or capabilities the CLI never installed in place,
- and clears the item from the install registry so [`list`](/docs/install/cli-reference/list/) and [`update`](/docs/install/cli-reference/update/) no longer track it.

If a capability was installed outside the CLI (added by hand to an agent's config), uninstall has no registry record of it and will report that it is not found.

## What flags and exit codes apply?

The [global flags](/docs/install/global-flags/) apply — `--json` for machine output, `--yes` to skip confirmation, `--non-interactive` to never prompt, and the usual `--color`/`--verbose`/`--quiet`. Common exit codes:

| Code | Meaning |
|---|---|
| `0` | Removed successfully. |
| `1` | A config write failed and was rolled back. |
| `3` | The name is not tracked in the install registry. |
| `4` | A filesystem operation was denied. |

As with install, a config write that fails part-way is rolled back, so an interrupted uninstall never leaves an agent in a half-edited state.

## Where do I go next?

- [saferskills install](/docs/install/cli-reference/install/) is the command this reverses.
- [saferskills list](/docs/install/cli-reference/list/) shows what is still installed across your agents.
- [saferskills doctor](/docs/install/cli-reference/doctor/) finds drift between the registry and the filesystem.
