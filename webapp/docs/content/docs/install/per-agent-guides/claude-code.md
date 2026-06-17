---
title: "Install in Claude Code"
description: "Where Claude Code loads installed skills from, the config file SaferSkills targets, and how to install with the trust score checked first."
updated: 2026-06-16
---
SaferSkills installs a skill into Claude Code by writing it under `~/.claude/skills/` and recording the install in `~/.claude/settings.json`. The `saferskills install` command detects Claude Code automatically, shows the capability's trust score and five-axis breakdown, and gates the write on the aggregate score before anything lands on disk. You can also install by hand from the public catalog.

## Where does Claude Code load installed skills from?

Claude Code loads skills from `~/.claude/skills/`, and its install registry lives in `~/.claude/settings.json`. SaferSkills writes a skill into the load path and records the install in the config file so it can later reverse exactly what it wrote.

| Setting | Value |
| --- | --- |
| Install path | `~/.claude/skills/` |
| Config file | `~/.claude/settings.json` |

These two paths are the agent manifest SaferSkills ships with. SaferSkills only writes into the load path and the config registry above — it does not modify any other part of your Claude Code configuration, and it never reads your conversation history, projects, or credentials.

## How do I install a skill with the CLI?

Run `install` with the catalog name of the capability. The CLI resolves the name to a catalog item, prints a digest, discloses that it is writing to Claude Code, and then applies the install score gate.

```bash
npx saferskills install mcp-server-github
```

Before any file is written, the CLI shows the aggregate score and the five [sub-scores](/docs/security-and-methodology/5-sub-scores/) (Security, Supply Chain, Maintenance, Transparency, Community). The gate is the aggregate: a capability below the minimum (default `90`, settable with `SAFERSKILLS_MIN_SCORE`) warns and asks for confirmation, and a red-tier item (score under 40) requires you to type its name. `--yes` confirms a below-threshold install; `--force` bypasses only the red-tier name prompt. See [`install`](/docs/install/cli-reference/install/) for the full flag set and [global flags](/docs/install/global-flags/) for `--json`, `--quiet`, and color controls.

To inspect a capability without installing it, use `info` (alias `check`):

```bash
npx saferskills info mcp-server-github
```

To reverse an install, `uninstall` undoes exactly what was written to `~/.claude/skills/` and `~/.claude/settings.json`:

```bash
npx saferskills uninstall mcp-server-github
```

## Can I install without the CLI?

Yes. Every scanned capability has a public report at `saferskills.ai/items/<slug>`, reachable from the [catalog](/docs/find-and-verify/browse-the-catalog/). Open the report, read the score and the findings, then follow the capability author's own installation instructions to place the files under `~/.claude/skills/`. The trade-off versus the CLI is that a manual install skips the score gate and the disclosure of which agent is being written to — so read the report first and decide before you copy anything. The report shows every rule that fired, with a quotable line of evidence, so you can judge a capability on the methodology rather than on a star count.

## What should I know about the trust boundary?

A skill in `~/.claude/skills/` is content the model reads as part of its working context, which makes it an [indirect prompt injection](/docs/concepts/glossary/#prompt-injection) surface: text in a skill body is exactly the untrusted external content the OWASP Top 10 ranks as the top LLM risk ([LLM01:2025](https://genai.owasp.org/llmrisk/llm01-prompt-injection/)). SaferSkills scans skill bodies for that class of risk before you install — invisible Unicode tag-channel instructions, fenced run-this imperatives, role-override jailbreaks — and surfaces each as a `rule_id` with the matched evidence.

A few boundary facts to keep in mind:

- **Auto-load at startup.** Claude Code's own loading behavior for files under `~/.claude/skills/` is determined by Claude Code, not by SaferSkills. Treat anything in that directory as live context for the model, and assume it can influence the model's behavior once present. SaferSkills does not change when or how Claude Code loads a skill — it only decides what you let land there.
- **No execution at scan time.** SaferSkills parses a capability as data. It never imports, evaluates, or shells out to the artifact it is scanning, on the server or in the CLI.
- **Determinism.** Every verdict is reproducible. A scan stamps the `rubric_version`, `engine_version`, and the scanned commit SHA, so the same bytes always score the same — there is no model, seed, or temperature in the verdict path. See [how scoring works](/docs/security-and-methodology/how-scoring-works/).
- **Re-check over time.** Scores can change when a repository changes — a [rug-pull](/docs/concepts/glossary/#drift--rug-pull) where the content hash drifts between scans is a tracked supply-chain signal. `update` re-verifies scores for what you have installed.

If you maintain a skill and a finding is wrong, you have a [right of reply](/docs/for-authors/disputing-findings/): prove ownership of the repository and post a public response, which triggers a re-scan.

## Related

- [Install a skill](/docs/install/install-a-skill/) — the cross-agent install walkthrough.
- [CLI reference: install](/docs/install/cli-reference/install/) — every flag and the score gate.
- [Managing your agents](/docs/concepts/managing-your-agents/) — what lives where across agents.
- [How scoring works](/docs/security-and-methodology/how-scoring-works/) — the rubric behind the number.
