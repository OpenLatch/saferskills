---
title: "saferskills agent"
description: "Run a behavioral Agent Scan against a running agent: mint, Ed25519 pack verify, bootstrap, poll, verdict."
updated: 2026-06-16
---
`saferskills agent` runs a behavioral [Agent Scan](/docs/concepts/agent-scan/) against your running agents — not their static files. For each agent it mints a run, pre-flight-verifies the Ed25519-signed assessment pack, prints a bootstrap prompt you paste into the agent, polls while the agent runs roughly 20 adversarial tests against **mock tools only** (zero real side effects), then renders a graded verdict. With no `--to` it detects your agents and lets you multi-select which to scan.

## How does the agent scan flow work?

The flow per agent is mint → verify → bootstrap → poll → verdict:

1. **Mint** a run and derive a per-run canary.
2. **Pre-flight-verify** the Ed25519-signed assessment pack with `verify_strict`. This is a **hard stop**: a released CLI with a baked verify key aborts on a missing, unknown, or mismatched signature — no prompt, no report. A dev or fork build with no baked key skips verification with a warning.
3. **Bootstrap** — the CLI prints a prompt you paste into your running agent.
4. The agent runs the test pack against mock tools and returns raw evidence.
5. **Poll** while it runs, then the SaferSkills cloud re-derives the canary deterministically, **grades** the evidence, and the CLI renders the [verdict](/docs/agent-scan/read-an-agent-report/).

Each chosen agent is scanned sequentially, a combined summary is printed, and the overall exit is the worst per-agent verdict.

```bash
npx saferskills agent
```

The pack signature verification is what makes the result trustworthy: the canary lives in the pack, so an unverified pack could leak it and let an agent fake a pass. See [run an agent scan](/docs/agent-scan/run-an-agent-scan/) for the paste-back walkthrough.

## Which agents does it scan?

With **no `--to`**, the CLI detects your agents and lets you multi-select (non-interactive or `--json` runs scan all detected). With `--to <id>` it scans the named agents, accepting any of the eight known agent ids even if not detected. Each report gets a stable memorable codename (such as `swift-otter`) generated per machine and platform and persisted in `~/.saferskills/agent-names.json`; `--name <name>` overrides it (on a multi-agent run the platform is appended, e.g. `my-bot-cursor`, so the cards stay distinct).

## What flags does agent accept?

| Flag | Effect |
|---|---|
| `--to <id>` | Scan a named agent (repeatable); accepts any of the 8 known ids even if not detected. |
| `--name <name>` | Override the auto-generated codename for the report. |
| `--fail-on <severity\|score:N\|band:tier>` | Map the verdict to an exit code (0 ok / 1 over threshold / 2 usage / 6 offline). |
| `--baseline <.agentscanignore\|prior.json>` | Suppress findings you have already accepted. |
| `--timeout <minutes>` | How long to wait for each agent to submit (default 45; a real run takes 10–40 min). |
| `--format json\|md` | Output format for the report. |
| `--private` | Produce an unlisted report. |
| `--print-skill` | Emit a static `SKILL.md` form instead of bootstrapping interactively. |
| `--submit-blob <file>` | Submit a paste-back blob the agent printed (for agents that cannot be polled). |
| `--no-telemetry` | Opt out of telemetry for this run. |

The [global flags](/docs/install/global-flags/) apply too. A `--fail-on` expression that can't be parsed exits `2` (usage).

## How is a verdict phrased?

The Agent Scan never says "secure," "safe," or "certified." A test result is reported as **observed vulnerable** or **not observed under pack v<version>**. The verdict enum is `vulnerable` / `not_observed` / `n_a` / `error`. Confidence and score are separate: a missing optional capability lowers confidence (the test is recorded `n_a`), never the score. See [behavioral scoring](/docs/agent-scan/behavioral-scoring/) for how the verdicts roll up.

## Where do I go next?

- [Run an agent scan](/docs/agent-scan/run-an-agent-scan/) walks the paste-and-poll flow end to end.
- [Read an agent report](/docs/agent-scan/read-an-agent-report/) explains the verdict and the test cards.
- [saferskills capability](/docs/install/cli-reference/scan/) is the **static** complement to this behavioral scan.
