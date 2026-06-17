---
title: "MCP Servers"
description: "An MCP server lets an agent connect external tools over the Model Context Protocol — here are its risks and how SaferSkills scans one."
updated: 2026-06-16
---
An MCP server is a process that exposes external tools to an agent over the Model Context Protocol (MCP), the open standard agents use to discover and call capabilities outside their own runtime. Because the agent reads each tool's name and description as trusted context, an MCP server's risks are tool poisoning, credential exposure, and unsafe tool calls. SaferSkills scans MCP servers fully in v1.

## What is an MCP server?

MCP is a cross-agent transport standard: a server advertises a set of tools — each with a name, a description, and a schema — and any MCP-capable agent can connect to it and call those tools. This is what lets one agent reach a database, a file system, a ticketing system, or an internal API without that integration being baked into the agent itself.

Because MCP is a shared protocol, an MCP server is the most broadly compatible [capability](/docs/concepts/glossary/#capability) kind — every supported agent (Claude Code, Cursor, Codex, Copilot, Windsurf, Cline, Gemini, OpenClaw) can consume it. That reach is also why a single poisoned MCP server can affect many users across many agents.

## What are the risks of an MCP server?

The agent treats a tool's description as instructions, so the description text is a security surface — the same surface attackers target. Three risks dominate:

- **Tool poisoning.** Malicious instructions hidden in a tool description are invisible to the user but read by the model. Invariant Labs coined the [Tool Poisoning Attack](https://invariantlabs.ai/blog/mcp-security-notification-tool-poisoning-attacks) in April 2025; their published proof-of-concept used a poisoned tool to extract a user's `~/.cursor/mcp.json` and SSH keys, and an "email shadowing" variant silently rerouted mail. OWASP lists this as [MCP03:2025 Tool Poisoning](https://owasp.org/www-project-mcp-top-10/) in the MCP Top 10. SaferSkills detects it with rules such as `SS-MCP-POISON-DESCRIPTION-CREEP-01` (oversized tool description), `SS-MCP-POISON-UNICODE-TAG-01` (invisible Unicode in a tool description), and `SS-MCP-POISON-SHADOW-TOOL-01` (a shadow tool registration).
- **Credential exposure.** An MCP server runs with the privileges of the connecting agent and can be steered to read tokens, key files, or environment secrets — the exact outcome the Invariant Labs PoC demonstrated.
- **Unsafe tool calls.** A server can declare capabilities it does not document, or invoke subprocesses the manifest never declares — SaferSkills flags this with `SS-MCP-CAP-UNDECLARED-01` (an undeclared subprocess capability).

The MCP layer has also produced named 2025 CVEs — for example [CVE-2025-6514](https://nvd.nist.gov/vuln/detail/CVE-2025-6514) (mcp-remote RCE) — underscoring that these are live, exploited surfaces.

## How does SaferSkills scan an MCP server?

SaferSkills runs the same deterministic static scan it runs for every [capability](/docs/concepts/glossary/#capability): a 0–100 [aggregate score](/docs/concepts/glossary/#aggregate-score) built from five weighted [sub-scores](/docs/concepts/glossary/#sub-score), with each [finding](/docs/concepts/glossary/#finding) anchored to a static [`rule_id`](/docs/concepts/glossary/#rule_id) and a quotable line of evidence. Tool-poisoning findings land in the Security sub-score (35% of the weight); an active `critical` finding caps the whole aggregate at ≤15. There is no LLM in the verdict path, so an MCP server's score is reproducible byte-for-byte.

A low score means **review before use** — read the findings and the evidence, then decide. See [How scoring works](/docs/concepts/how-scoring-works/) for the full model, or the [live methodology page](/methodology) for every MCP rule.

## Related reading

- [How scoring works](/docs/concepts/how-scoring-works/) — the 0–100 model in one page.
- [Glossary](/docs/concepts/glossary/) — including [tool poisoning](/docs/concepts/glossary/#tool-poisoning) and [prompt injection](/docs/concepts/glossary/#prompt-injection).
- [Skills](/docs/concepts/skills/) — the other fully-scanned capability kind in v1.
