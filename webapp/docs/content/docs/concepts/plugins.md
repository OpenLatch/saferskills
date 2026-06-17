---
title: "Plugins"
description: "A plugin bundles several capabilities into one package — combining their risk surfaces. Full scanning is on the v1.2 roadmap."
updated: 2026-06-16
---
A plugin is a package that bundles several capabilities — skills, MCP servers, hooks, and configuration — into one installable unit. That convenience also combines their risk surfaces: a single plugin install can introduce an injectable skill body, a poisonable MCP tool description, and an auto-executing shell hook at once. Plugin detection rules ship in the rubric, with full scanning on the v1.2 roadmap.

## What does a plugin bundle?

A plugin is the "everything in one install" [capability](/docs/concepts/glossary/#capability) kind. Rather than installing a skill, then an MCP server, then a hook separately, a plugin packages them together so a single command sets up a whole workflow. In the Claude Code family a plugin is identified by a `plugin.json` or a `.claude-plugin/` directory; plugins are compatible with Claude Code and OpenClaw.

The convenience is real, and so is the trade-off: you are accepting every capability the bundle contains, in one decision, often without reading each one.

## What is the combined risk surface of a plugin?

A plugin inherits the security surface of each capability it ships, so its risk is the union of theirs:

- The [skill](/docs/concepts/skills/) bodies it includes can carry [prompt injection](/docs/concepts/glossary/#prompt-injection) or request credential access.
- The [MCP server](/docs/concepts/mcp-servers/) it bundles can be vulnerable to [tool poisoning](/docs/concepts/glossary/#tool-poisoning).
- The [hooks](/docs/concepts/hooks/) it registers run shell on lifecycle events, the highest-risk surface of all.

On top of those, a plugin's broad reach makes it a natural target for credential exfiltration. SaferSkills ships PLUGIN rules for exactly this class — `SS-PLUGIN-SECRET-EXFIL-GH-TOKEN-01` (a GitHub token in source, `critical`), `SS-PLUGIN-SECRET-EXFIL-AWS-FILES-01` (an AWS credentials-file read, `critical`), `SS-PLUGIN-SECRET-EXFIL-SSH-01` (SSH private-key access), and `SS-PLUGIN-SECRET-EXFIL-ENV-NET-01` (an environment read followed by a network call). Because one install carries many capabilities, the [Sonatype 2024 supply-chain report](https://www.sonatype.com/state-of-the-software-supply-chain/introduction)'s 156% year-over-year rise in malicious packages is most consequential where a single bundle can deliver several at once.

## How does SaferSkills handle plugins?

The PLUGIN detection category exists in the rubric today and uses the same [`rule_id`](/docs/concepts/glossary/#rule_id) grammar and [scoring model](/docs/concepts/how-scoring-works/) as every other [detection category](/docs/security-and-methodology/detection-categories/). Skills and MCP servers are the fully scanned capabilities in v1; broader plugin coverage — scoring the bundle as the union of its parts — is a forward-looking item on the v1.2 roadmap. As always, an active `critical` finding caps the whole aggregate at ≤15, and a low score means **review every capability the plugin bundles before you install it**.

## Where do I go next?

- [Skills](/docs/concepts/skills/), [MCP servers](/docs/concepts/mcp-servers/), [Hooks](/docs/concepts/hooks/) — the capabilities a plugin can bundle.
- [Glossary](/docs/concepts/glossary/) — including [plugin](/docs/concepts/glossary/#plugin) and [capability](/docs/concepts/glossary/#capability).
- [How scoring works](/docs/concepts/how-scoring-works/) — the model applied to every capability kind.
