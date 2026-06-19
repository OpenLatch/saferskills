---
title: "Install in Cline"
description: "How SaferSkills handles Cline — a VS Code extension, not a filesystem path — and how to verify a capability's trust score first."
updated: 2026-06-16
---
Cline is a VS Code extension, not a configuration directory, so SaferSkills identifies it by its extension URI (`vscode://extensions/cline`) rather than a home-directory path. The `saferskills install` command detects Cline among your agents, shows the capability's trust score and five-axis breakdown, discloses where it writes, and gates on the aggregate score before anything lands. Because Cline lives inside VS Code, install steps follow the extension rather than a `~/.cline/` folder.

## Where does Cline live?

Cline is a VS Code extension. The agent manifest records it as the extension URI, not a filesystem load path, which is why both columns below point at VS Code rather than a home directory.

| Setting | Value |
| --- | --- |
| Install path | `vscode://extensions/cline` |
| Config file | `(VS Code extension)` |

Because Cline is an extension and not a path SaferSkills owns, the precise on-disk location of any capability is managed by the extension inside VS Code. SaferSkills targets the extension Cline exposes — it does not write into VS Code's internal storage on its own beyond what the install flow discloses.

## How do I install with the CLI?

Run `install` with the catalog name. The CLI resolves the name to a catalog item, prints a digest, discloses which detected agents it will affect (Cline among them, identified by its extension), and then applies the install score gate.

```bash
npx saferskills install mcp-server-github
```

Before anything is applied, the CLI shows the aggregate score and the five [sub-scores](/docs/security-and-methodology/5-sub-scores/) (Security, Supply Chain, Maintenance, Transparency, Community). The gate is the aggregate: below the minimum (default `90`, set with `SAFERSKILLS_MIN_SCORE`) it warns and confirms; a red-tier item (score under 40) requires typing its name. `--yes` confirms a below-threshold install; `--force` bypasses only the red-tier name prompt. See [`install`](/docs/install/cli-reference/install/) and the [global flags](/docs/install/global-flags/).

Inspect first with `info` (alias `check`):

```bash
npx saferskills info mcp-server-github
```

`uninstall` reverses exactly what the CLI applied for Cline:

```bash
npx saferskills uninstall mcp-server-github
```

## Can I install without the CLI?

Yes. Find the capability in the [catalog](/docs/find-and-verify/browse-the-catalog/), open its public report at `saferskills.ai/items/<slug>`, read the score and findings, then add it through Cline's own interface in VS Code. Because Cline is an extension, you configure it inside the editor rather than by editing a home-directory file. A manual install skips the CLI's score gate and write-disclosure, so read the report — every rule that fired, with a quotable line of evidence — before you proceed.

## What should I know about the trust boundary?

A capability Cline loads is content the model reads, which makes it an [indirect prompt injection](/docs/concepts/glossary/#prompt-injection) surface: the body is exactly the untrusted external content OWASP ranks as the top LLM risk ([LLM01:2025](https://genai.owasp.org/llmrisk/llm01-prompt-injection/)). MCP tool descriptions you add through Cline are an additional [tool poisoning](/docs/concepts/glossary/#tool-poisoning) surface — OWASP MCP03:2025 in the [MCP Top 10](https://owasp.org/www-project-mcp-top-10/). SaferSkills scans for both classes and reports each as a `rule_id` with the matched evidence, before you install.

A few boundary facts:

- **Auto-load and isolation are the extension's.** Because Cline is a VS Code extension, its loading and isolation behavior is governed by the extension and the editor, not by SaferSkills. Treat anything Cline loads as live context the model can act on.
- **No execution at scan time.** SaferSkills parses a capability as data — it never imports, evaluates, or runs the artifact it scans.
- **Determinism.** Each verdict stamps `rubric_version`, `engine_version`, and the scanned commit SHA, so identical bytes always score the same. No LLM sits in the verdict path. See [how scoring works](/docs/security-and-methodology/how-scoring-works/).
- **Re-check over time.** A [rug-pull](/docs/concepts/glossary/#drift--rug-pull) — content-hash drift between scans — is a tracked supply-chain signal; `update` re-verifies installed scores.

If you maintain a capability and a finding is wrong, the [right of reply](/docs/for-authors/disputing-findings/) lets you prove ownership and post a public response that triggers a re-scan.

## Where do I go next?

- [Install a skill](/docs/install/install-a-skill/) — the cross-agent install walkthrough.
- [Teach your agent to use SaferSkills](/docs/install/saferskills-skill/) — install the skill so this agent runs SaferSkills on its own.
- [CLI reference: install](/docs/install/cli-reference/install/) — every flag and the score gate.
- [Managing your agents](/docs/concepts/managing-your-agents/) — what lives where across agents.
- [How scoring works](/docs/security-and-methodology/how-scoring-works/) — the rubric behind the number.
