---
title: "Run an Agent Scan"
description: "Start an Agent Scan three ways — copy-paste prompt, the saferskills agent CLI, or a SKILL.md — and what the ~2–3 minute setup does."
updated: 2026-06-16
---

You can start an Agent Scan three ways: paste a bootstrap prompt into your agent, run `saferskills agent` from your terminal, or (in a future path) load a `SKILL.md`. All three drive the same flow — mint a run, verify the Ed25519-signed test pack, hand your agent a bootstrap prompt, then poll for the verdict. The setup is fast, a couple of minutes; the agent's own test run takes longer and the CLI waits for it.

## What are the three activation paths?

There are three ways to kick off the same behavioral run. **Copy-paste prompt** — paste a bootstrap prompt directly into a running agent; the agent runs the pack and prints evidence you submit back. **`saferskills agent`** — the CLI detects your agents, mints the run, verifies the pack, prints the bootstrap prompt, and polls for you. **`SKILL.md`** — a future static-skill form (the CLI can already emit one with `--print-skill`) you load into your agent. The CLI path is the most automated; the copy-paste path needs nothing installed.

## How do I run it with the CLI?

The `saferskills agent` command detects your agents and walks each one through the flow. With no `--to` it lets you multi-select which detected agents to scan; `--to <id>` (repeatable) names them explicitly and accepts any of the 8 known agent ids even if not detected.

```bash
npx saferskills agent                 # detect agents, multi-select which to scan
npx saferskills agent --to claude-code --to cursor
npx saferskills agent --private       # produce an unlisted report
```

Each chosen agent is scanned **sequentially** and a combined summary is printed; the overall exit code is the **worst per-agent verdict**. Useful flags: `--fail-on <severity|score:N|band:tier>` maps the verdict to an exit code for CI gating, `--baseline <.agentscanignore|prior.json>` suppresses accepted findings, `--timeout <minutes>` sets how long to wait for each agent to submit (default **45**), `--format json|md`, and `--print-skill` to emit the static `SKILL.md` form instead. Global flags such as `--json`, `--no-color`, and `--non-interactive` behave as documented in the [CLI reference](/docs/install/cli-reference/scan-agent/).

## What happens during the ~2–3 minute setup?

The setup is a fixed five-step handshake; the agent's test run is what takes longer. In order:

1. **Mint** — the CLI mints a run and a per-run canary is derived for it.
2. **Verify** — the CLI pre-flight-verifies the **Ed25519-signed** assessment pack with `verify_strict` over the exact served bytes, fetched from a token-gated endpoint. A signature mismatch is a **hard stop**: no bootstrap prompt is printed and the run aborts. A released CLI fails closed; a source or fork build with no baked public key skips verification with a warning.
3. **Bootstrap prompt** — the CLI prints a bootstrap prompt. You paste it into your agent (or, on the copy-paste path, you start here).
4. **Poll** — your agent runs ~20 adversarial prompt-injection, tool-poisoning, and data-exfiltration tests against **mock tools only — zero real side effects** — and submits raw evidence. The CLI polls for completion.
5. **Verdict** — the SaferSkills cloud re-derives the canary, grades the evidence deterministically, and the CLI renders the verdict.

Step 2 is the security anchor: verifying the signed pack before printing anything is what stops a tampered pack from leaking the per-run canary. The agent's own run in step 4 commonly takes 10–40 minutes for a real agent; the CLI waits up to `--timeout` minutes (Ctrl-C bails early).

## Where does my report live, and what's next?

Each run becomes an Agent Report with a permalink. By default the report is public and appears in the [agents directory](/agents); `--private` keeps it **unlisted**, reachable only via its unguessable share link. To read the result, see [Read an Agent Report](/docs/agent-scan/read-an-agent-report/). For the meaning of the 0–100 score, see [behavioral scoring](/docs/agent-scan/behavioral-scoring/).
