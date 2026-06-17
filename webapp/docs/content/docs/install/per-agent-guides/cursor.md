---
title: "Install in Cursor"
description: "Where Cursor registers MCP servers, the config file SaferSkills targets, and how to install with the trust score checked first."
updated: 2026-06-16
---
In Cursor, SaferSkills works against the MCP server registry at `~/.cursor/mcp.json` — both the load path and the config file for what you install. The `saferskills install` command detects Cursor automatically, shows the capability's trust score and five-axis breakdown, discloses that it is writing to `mcp.json`, and gates on the aggregate score before any change lands. You can also install by hand from the public catalog.

## Where does Cursor register installed capabilities?

Cursor configures MCP servers in `~/.cursor/mcp.json`, which serves as both the load path and the config file. SaferSkills reads and writes that one file when it installs or removes an MCP server for Cursor, and reverses exactly its own changes on uninstall.

| Setting | Value |
| --- | --- |
| Install path | `~/.cursor/mcp.json` |
| Config file | `~/.cursor/mcp.json` |

This path is the agent manifest SaferSkills ships with. SaferSkills only edits the MCP entries it added — it does not rewrite the rest of your `mcp.json` and never touches other Cursor settings.

## How do I install an MCP server with the CLI?

Run `install` with the catalog name. The CLI resolves the name to a catalog item, prints a digest, discloses that it is writing to Cursor's `mcp.json`, and then applies the install score gate.

```bash
npx saferskills install mcp-server-github
```

Before the file is edited, the CLI shows the aggregate score and the five [sub-scores](/docs/security-and-methodology/5-sub-scores/) (Security, Supply Chain, Maintenance, Transparency, Community). The gate is the aggregate: below the minimum (default `90`, set via `SAFERSKILLS_MIN_SCORE`) it warns and confirms; a red-tier item (score under 40) requires you to type its name. `--yes` confirms a below-threshold install; `--force` bypasses only the red-tier name prompt. See [`install`](/docs/install/cli-reference/install/) and the [global flags](/docs/install/global-flags/).

To inspect first, use `info` (alias `check`):

```bash
npx saferskills info mcp-server-github
```

`uninstall` reverses exactly the entry the CLI added to `~/.cursor/mcp.json`:

```bash
npx saferskills uninstall mcp-server-github
```

## Can I install without the CLI?

Yes. Find the capability in the [catalog](/docs/find-and-verify/browse-the-catalog/), open its public report at `saferskills.ai/items/<slug>`, read the score and the findings, then add the server to `~/.cursor/mcp.json` yourself using the author's instructions. A manual edit skips the CLI's score gate and its write-disclosure, so read the report — every rule that fired, with a quotable line of evidence — before you paste anything into your config.

## What should I know about the trust boundary?

An MCP server's tool descriptions are read by the model, which makes them a [tool poisoning](/docs/concepts/glossary/#tool-poisoning) surface: instructions hidden in a tool description are invisible to you but visible to the model. This is not theoretical. Invariant Labs demonstrated a [tool poisoning attack](https://invariantlabs.ai/blog/mcp-security-notification-tool-poisoning-attacks) whose published proof-of-concept used a poisoned MCP tool to exfiltrate a user's `~/.cursor/mcp.json` and SSH keys — the exact file you are editing here. OWASP tracks the same class as MCP03:2025 in its [MCP Top 10](https://owasp.org/www-project-mcp-top-10/). Tool poisoning is why SaferSkills scans MCP tool descriptions for hidden-instruction patterns — invisible Unicode tag-channel text, zero-width and bidi smuggling, oversized description creep, shadow-tool registration — before you install.

A few boundary facts:

- **Auto-load behavior is Cursor's.** Whether and when Cursor starts a server listed in `mcp.json` is Cursor's behavior, not SaferSkills'. Treat every entry in that file as a live tool surface the model can call once it is present.
- **No execution at scan time.** SaferSkills parses a capability as data — it never imports, evaluates, or runs the artifact it scans.
- **Determinism.** Each verdict stamps `rubric_version`, `engine_version`, and the scanned commit SHA, so the same bytes always score the same. There is no LLM in the verdict path. See [how scoring works](/docs/security-and-methodology/how-scoring-works/).
- **Re-check over time.** A [rug-pull](/docs/concepts/glossary/#drift--rug-pull) — content-hash drift between scans — is a tracked supply-chain signal; `update` re-verifies scores for what you have installed.

If you maintain a server and disagree with a finding, the [right of reply](/docs/for-authors/disputing-findings/) lets you prove ownership and post a public response that triggers a re-scan.

## Related

- [Install a skill](/docs/install/install-a-skill/) — the cross-agent install walkthrough.
- [CLI reference: install](/docs/install/cli-reference/install/) — every flag and the score gate.
- [What is an MCP server?](/docs/concepts/mcp-servers/) — the capability kind and its risks.
- [How scoring works](/docs/security-and-methodology/how-scoring-works/) — the rubric behind the number.
