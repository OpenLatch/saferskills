---
title: "saferskills install"
description: "Install a Skill or MCP server to your detected agents, gated on the aggregate trust score (default min 90)."
updated: 2026-06-16
---
`saferskills install <name>` resolves a name to a catalog item, shows its digest (aggregate score plus the five-axis breakdown), discloses which detected agents it will write to, then gates on the [aggregate score](/docs/concepts/how-scoring-works/) before writing anything. Below the minimum score (default 90) it warns and asks you to confirm; a red-tier item (score under 40) requires you to type the item name. The CLI installs Skills and MCP servers only.

## How do I install a capability?

Pass the item name. The CLI detects your agents, resolves the name against the public catalog, and writes the capability's config to every compatible agent:

```bash
npx saferskills install mcp-server-github
```

Before writing, it prints a digest — the global score and the breakdown across security, supply chain, maintenance, transparency, and community — and lists exactly which agents will be modified, so there are no silent edits. The eight supported agents and their config paths are covered in the [per-agent guides](/docs/install/per-agent-guides/claude-code/).

## How does the score gate work?

Install gates on the **aggregate score**, and the threshold resolves in this order: the `SAFERSKILLS_MIN_SCORE` environment variable, then `min_score` in `~/.saferskills/config.toml`, then the default of **90**.

- An item **at or above** the minimum installs after you confirm the agent list.
- An item **below** the minimum (or one with no score yet) warns and asks before installing. Pass `--yes` to confirm a below-threshold install non-interactively.
- A **red-tier** item — aggregate score under 40, the Block band — additionally requires you to type the item's name to proceed. Only `--force` bypasses that type-the-name gate.

A low score is a prompt to review, not a verdict that the capability is unusable — SaferSkills publishes methodology, not endorsements. The score reflects rules that fired; read the [scan report](/docs/find-and-verify/read-a-scan-report/) to see exactly which ones and why. Note that one active critical finding caps the whole aggregate at 15 and one active high finding caps it at 45, so a single [prompt injection](/docs/concepts/glossary/#prompt-injection) or supply-chain finding pulls the score into the gated range regardless of the other axes.

## What flags does install accept?

| Flag | Effect |
|---|---|
| `--yes` | Confirm a below-threshold install without an interactive prompt. |
| `--force` | Bypass the red-tier type-the-name gate. Does not lower the score itself. |
| `--json` | Emit machine-readable output on stdout (suppresses the human banner). |
| `--non-interactive` (alias `--no-input`) | Never prompt; a gate that needs confirmation fails with a usage error instead. |

The full set of [global flags](/docs/install/global-flags/) — `--color`, `-v/--verbose`, `-q/--quiet` — applies here too. To raise or lower the gate for a single run, set the environment variable inline:

```bash
SAFERSKILLS_MIN_SCORE=80 npx saferskills install mcp-server-github
```

## What exit codes can install return?

| Code | Meaning |
|---|---|
| `0` | Installed successfully. |
| `1` | You declined a gate, or a config write failed and was rolled back. |
| `2` | A required choice could not be made non-interactively (a gate hit without `--yes`/`--force`). |
| `3` | The name did not resolve to any catalog item. |
| `4` | A filesystem operation was denied. |
| `5` | The item is already installed and collided with the registry. |
| `6` | The API was unreachable, rate-limited, or offline. |

A config write that fails mid-flight rolls back its partial edits, so a failed install never leaves an agent half-configured. See [global flags](/docs/install/global-flags/) for the complete exit-code reference.

## Where do I go next?

- [saferskills uninstall](/docs/install/cli-reference/uninstall/) reverses exactly what install wrote.
- [saferskills update](/docs/install/cli-reference/update/) refreshes installed capabilities and re-verifies scores.
- [saferskills list](/docs/install/cli-reference/list/) shows everything installed across your agents.
- [Install a skill](/docs/install/install-a-skill/) walks the flow with per-agent tabs.
