---
title: "Global Flags & Exit Codes"
description: "The flags on every saferskills command, the environment variables they read, and the exact 0/1/2/3/4/5/6/130 exit-code contract."
updated: 2026-06-16
---

Every `saferskills` command accepts the same set of global flags — `--json`, `--color`/`--no-color`, `-v`/`--verbose`, `-q`/`--quiet`, `--yes`, `--force`, and `--non-interactive` (alias `--no-input`) — reads a handful of `SAFERSKILLS_*` environment variables, and returns a stable exit code (`0` ok, `1` generic/findings-block, `2` usage, `3` not-found, `4` permission, `5` conflict, `6` network/offline, `130` SIGINT). Output discipline is fixed: **stdout is machine data, stderr is everything human.**

## What flags work on every command?

These flags are global — they apply to `info`, `install`, `uninstall`, `update`, `list`, `search`, `doctor`, `capability`, `agent`, and `completion` alike:

| Flag | Effect |
|---|---|
| `--json` | Emit machine-readable output on stdout. Suppresses the banner and human chatter. |
| `--color <auto\|always\|never>` | Control ANSI color. Defaults to `auto`. |
| `--no-color` | Force color off (equivalent to `--color never`). |
| `-v`, `--verbose` | Increase log detail on stderr. |
| `-q`, `--quiet` | Suppress non-essential human output. |
| `--yes` | Auto-confirm prompts (e.g. a below-threshold install). |
| `--force` | Bypass the red-tier name gate on install. |
| `--non-interactive`, `--no-input` | Never prompt; assume non-TTY behavior. |

```bash
npx saferskills --json info mcp-server-github
npx saferskills --non-interactive install mcp-server-github --yes
```

## Why is output split between stdout and stderr?

So you can pipe machine output without it being polluted by human text. **stdout carries machine data only** (JSON when `--json` is set); **stderr carries everything human** — steps, warnings, errors, and the two-line `SaferSkills` banner. That split lets you do this safely:

```bash
npx saferskills --json info mcp-server-github > result.json
```

`result.json` contains only the data envelope; the banner and any progress lines went to stderr. The banner is suppressed under `--json` and `--quiet`, and for the `completion` and `man` outputs.

## How does the CLI decide whether to use color?

Color resolves from `--color`/`--no-color` first, then the standard environment controls. The CLI honors `NO_COLOR` (disable), `CLICOLOR_FORCE` (force on), and `TERM=dumb` (disable). An explicit `--color <auto|always|never>` overrides those environment variables.

## What environment variables does the CLI read?

The CLI reads a small, closed set of `SAFERSKILLS_*` variables plus the standard color and opt-out conventions. Precedence across all configuration is **CLI flags → `SAFERSKILLS_*` env → `config.toml` → defaults**.

| Variable | Effect |
|---|---|
| `SAFERSKILLS_API_URL` | API origin to call. Precedence: env → `config.toml` `api_url` → `https://saferskills.ai`. |
| `SAFERSKILLS_MIN_SCORE` | Minimum aggregate score (0–100) that installs without a confirm. Precedence: env → `config.toml` `min_score` → `90`. |
| `SAFERSKILLS_DIR` | Override the state directory (default `~/.saferskills/`, which holds `config.toml` and `installs.json`). |
| `SAFERSKILLS_NO_TELEMETRY` | Disable **all** telemetry — usage analytics and install reporting. `DO_NOT_TRACK` and `CI` are honored the same way. |
| `SAFERSKILLS_TELEMETRY` | Force usage analytics on (`1`/`true`) or off (`0`), skipping the first-run prompt. Does not affect install reporting. |
| `NO_COLOR` / `CLICOLOR_FORCE` / `TERM=dumb` | Standard color controls; `--color` overrides them. |

Two opt-out conventions are honored exactly like `SAFERSKILLS_NO_TELEMETRY`: `DO_NOT_TRACK` and `CI`. Source and fork builds send nothing on either telemetry channel regardless of these variables, because telemetry requires a key baked in at release time. See [the telemetry section of the install reference](/docs/install/cli-reference/install/) and the [privacy policy](/privacy) for what is — and is not — collected.

## What does each exit code mean?

Every command returns one of a fixed set of exit codes, so you can branch on the result in a script or CI step:

| Code | Meaning |
|---|---|
| `0` | Success. |
| `1` | Generic failure, or a findings-block (e.g. an install refused on score, or `agent` over a `--fail-on` threshold). |
| `2` | Usage error (invalid arguments — emitted by the argument parser). |
| `3` | Not found (the named capability could not be resolved). |
| `4` | Permission error (a filesystem write was denied). |
| `5` | Conflict (e.g. an install/registry state collision). |
| `6` | Network, rate-limit, or offline error. |
| `130` | Interrupted (Ctrl-C / SIGINT). |

```bash
npx saferskills --non-interactive install mcp-server-github
if [ $? -ne 0 ]; then
  echo "install did not complete cleanly" >&2
fi
```

:::note
The `agent` command maps each behavioral verdict to a subset of these codes via `--fail-on` (`0` ok / `1` over threshold / `2` usage / `6` offline). See the [Agent Scan reference](/docs/install/cli-reference/scan-agent/).
:::

## Where do I go next?

- [Install a Skill](/docs/install/install-a-skill/) — the canonical install flow and the score gate.
- [CLI reference](/docs/install/cli-reference/install/) — every command in detail.
- [Static component scan (`capability`)](/docs/install/cli-reference/scan/) and [behavioral Agent Scan (`agent`)](/docs/install/cli-reference/scan-agent/) — the two scan commands and their per-command flags.
