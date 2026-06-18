---
title: "Install in GH Copilot"
description: "Where GitHub Copilot loads installed capabilities from, the path SaferSkills targets, and how to install with the trust score checked first."
updated: 2026-06-16
---
SaferSkills installs into GitHub Copilot by writing under `~/.github/copilot/`, which is both the load path and the config location in the agent manifest. The `saferskills install` command detects Copilot automatically, shows the capability's trust score and five-axis breakdown, discloses that it is writing to Copilot, and gates on the aggregate score before anything lands on disk. You can also install by hand from the public catalog.

## Where does GitHub Copilot load installed capabilities from?

GitHub Copilot loads from `~/.github/copilot/`, and the same directory is the config location SaferSkills records against. SaferSkills writes a capability into that path on install and reverses exactly what it wrote on uninstall.

| Setting | Value |
| --- | --- |
| Install path | `~/.github/copilot/` |
| Config file | `~/.github/copilot/` |

This path is the agent manifest SaferSkills ships with. SaferSkills only manages the capabilities it placed there — it does not modify the rest of your Copilot configuration.

## How do I install with the CLI?

Run `install` with the catalog name. The CLI resolves the name to a catalog item, prints a digest, discloses that it is writing to Copilot, and then applies the install score gate.

```bash
npx saferskills install mcp-server-github
```

Before any file is written, the CLI shows the aggregate score and the five [sub-scores](/docs/security-and-methodology/5-sub-scores/) (Security, Supply Chain, Maintenance, Transparency, Community). The gate is the aggregate: below the minimum (default `90`, set with `SAFERSKILLS_MIN_SCORE`) it warns and confirms; a red-tier item (score under 40) requires typing its name. `--yes` confirms a below-threshold install; `--force` bypasses only the red-tier name prompt. See [`install`](/docs/install/cli-reference/install/) and the [global flags](/docs/install/global-flags/).

Inspect first with `info` (alias `check`):

```bash
npx saferskills info mcp-server-github
```

`uninstall` reverses exactly what the CLI wrote under `~/.github/copilot/`:

```bash
npx saferskills uninstall mcp-server-github
```

## Can I install without the CLI?

Yes. Find the capability in the [catalog](/docs/find-and-verify/browse-the-catalog/), open its public report at `saferskills.ai/items/<slug>`, read the score and findings, then place the files under `~/.github/copilot/` per the author's instructions. A manual install skips the score gate and the write-disclosure, so read the report — every rule that fired, with a quotable line of evidence — before you copy anything.

## What should I know about the trust boundary?

A capability under `~/.github/copilot/` is content the model reads, which makes it an [indirect prompt injection](/docs/concepts/glossary/#prompt-injection) surface: the body is exactly the untrusted external content OWASP ranks as the top LLM risk ([LLM01:2025](https://genai.owasp.org/llmrisk/llm01-prompt-injection/)). SaferSkills scans for that class — invisible Unicode tag-channel injection, fenced run-this imperatives, role-override jailbreaks — and reports each as a `rule_id` with the matched evidence.

A few boundary facts:

- **Auto-load behavior is Copilot's.** When and how Copilot loads what lives in `~/.github/copilot/` is determined by Copilot, not SaferSkills. Treat anything in that directory as live context the model can act on.
- **No execution at scan time.** SaferSkills parses a capability as data — it never imports, evaluates, or runs the artifact it scans.
- **Determinism.** Each verdict stamps `rubric_version`, `engine_version`, and the scanned commit SHA, so identical bytes always score the same. No LLM sits in the verdict path. See [how scoring works](/docs/security-and-methodology/how-scoring-works/).
- **Re-check over time.** A [rug-pull](/docs/concepts/glossary/#drift--rug-pull) — content-hash drift between scans — is a tracked supply-chain signal; `update` re-verifies installed scores.

If you maintain a capability and a finding is wrong, the [right of reply](/docs/for-authors/disputing-findings/) lets you prove ownership and post a public response that triggers a re-scan.

## Where do I go next?

- [Install a skill](/docs/install/install-a-skill/) — the cross-agent install walkthrough.
- [CLI reference: install](/docs/install/cli-reference/install/) — every flag and the score gate.
- [Managing your agents](/docs/concepts/managing-your-agents/) — what lives where across agents.
- [How scoring works](/docs/security-and-methodology/how-scoring-works/) — the rubric behind the number.
