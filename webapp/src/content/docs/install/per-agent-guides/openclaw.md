---
title: "Install in OpenClaw"
description: "Where OpenClaw loads installed skills from, the openclaw.json config it records against, and how to install with the trust score checked first."
updated: 2026-06-16
---
SaferSkills installs a skill into OpenClaw by writing it under `~/.openclaw/skills/` and recording the install in `openclaw.json`. The `saferskills install` command detects OpenClaw automatically, shows the capability's trust score and five-axis breakdown, discloses that it is writing to OpenClaw, and gates on the aggregate score before any file lands. You can also install by hand from the public catalog.

## Where does OpenClaw load installed skills from?

OpenClaw loads skills from `~/.openclaw/skills/`, and its install registry lives in `openclaw.json`. SaferSkills writes a skill into the load path, records the install in the config file, and reverses exactly what it wrote on uninstall.

| Setting | Value |
| --- | --- |
| Install path | `~/.openclaw/skills/` |
| Config file | `openclaw.json` |

These paths are the agent manifest SaferSkills ships with. SaferSkills writes only into the load path and the entries it owns in `openclaw.json` — it does not rewrite the rest of your OpenClaw configuration.

## How do I install a skill with the CLI?

Run `install` with the catalog name. The CLI resolves the name to a catalog item, prints a digest, discloses that it is writing to OpenClaw, and then applies the install score gate.

```bash
npx saferskills install mcp-server-github
```

Before any file is written, the CLI shows the aggregate score and the five [sub-scores](/docs/security-and-methodology/5-sub-scores/) (Security, Supply Chain, Maintenance, Transparency, Community). The gate is the aggregate: below the minimum (default `90`, set with `SAFERSKILLS_MIN_SCORE`) it warns and confirms; a red-tier item (score under 40) requires typing its name. `--yes` confirms a below-threshold install; `--force` bypasses only the red-tier name prompt. See [`install`](/docs/install/cli-reference/install/) and the [global flags](/docs/install/global-flags/).

Inspect first with `info` (alias `check`):

```bash
npx saferskills info mcp-server-github
```

`uninstall` reverses exactly what the CLI wrote under `~/.openclaw/skills/` and in `openclaw.json`:

```bash
npx saferskills uninstall mcp-server-github
```

## Can I install without the CLI?

Yes. Find the capability in the [catalog](/docs/find-and-verify/browse-the-catalog/), open its public report at `saferskills.ai/items/<slug>`, read the score and findings, then place the skill under `~/.openclaw/skills/` and register it in `openclaw.json` per the author's instructions. A manual install skips the score gate and the write-disclosure, so read the report — every rule that fired, with a quotable line of evidence — before you copy anything.

## What should I know about the trust boundary?

A skill in `~/.openclaw/skills/` is content the model reads, which makes it an [indirect prompt injection](/docs/concepts/glossary/#prompt-injection) surface: a skill body is exactly the untrusted external content OWASP ranks as the top LLM risk ([LLM01:2025](https://genai.owasp.org/llmrisk/llm01-prompt-injection/)). SaferSkills scans skill bodies for that class — invisible Unicode tag-channel injection, fenced run-this imperatives, role-override jailbreaks — and reports each as a `rule_id` with the matched evidence.

A few boundary facts:

- **Auto-load behavior is OpenClaw's.** When and how OpenClaw loads a skill from `~/.openclaw/skills/` is determined by OpenClaw, not SaferSkills. Treat anything in that directory as live context the model can act on.
- **No execution at scan time.** SaferSkills parses a capability as data — it never imports, evaluates, or shells out to the artifact it scans.
- **Determinism.** Each verdict stamps `rubric_version`, `engine_version`, and the scanned commit SHA, so identical bytes always score the same. No LLM sits in the verdict path. See [how scoring works](/docs/security-and-methodology/how-scoring-works/).
- **Re-check over time.** A [rug-pull](/docs/concepts/glossary/#drift--rug-pull) — content-hash drift between scans — is a tracked supply-chain signal; `update` re-verifies installed scores.

If you maintain a skill and a finding is wrong, the [right of reply](/docs/for-authors/disputing-findings/) lets you prove ownership and post a public response that triggers a re-scan.

## Where do I go next?

- [Install a skill](/docs/install/install-a-skill/) — the cross-agent install walkthrough.
- [Teach your agent to use SaferSkills](/docs/install/saferskills-skill/) — install the skill so this agent runs SaferSkills on its own.
- [CLI reference: install](/docs/install/cli-reference/install/) — every flag and the score gate.
- [What is a skill?](/docs/concepts/skills/) — the capability kind and its risks.
- [How scoring works](/docs/security-and-methodology/how-scoring-works/) — the rubric behind the number.
