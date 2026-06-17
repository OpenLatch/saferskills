---
title: "Detection Categories"
description: "The five rule categories — MCP, SKILL, RULES, HOOKS, PLUGIN — and the rule families inside each."
updated: 2026-06-16
author: "SaferSkills Team"
---
SaferSkills organizes its detection rules into five categories named for the artifact kind they target: MCP, SKILL, RULES, HOOKS, and PLUGIN. Within those categories, rules group into families by what they look for — prompt injection, obfuscation, dangerous shell, supply chain, transparency, maintenance, and community. Every rule carries a stable `SS-<CATEGORY>-<NAME>-NN` ID, a severity, and the sub-score it contributes to.

## What are the five detection categories?

The category is the closed set of artifact kinds a rule can target — `MCP`, `SKILL`, `RULES`, `HOOKS`, `PLUGIN` — and it forms the middle segment of every rule ID. A rule's category determines which capabilities it is matched against during a scan; a HOOKS rule only fires on a discovered hook, an MCP rule only on a discovered MCP server, and so on. Some rules apply across every kind (for example, a missing-LICENSE check applies to all of them), but each is filed under one category for its rule ID.

These categories are about *where* a rule fires. The seven rule **families** below cut across the categories and describe *what* a rule looks for. A single category like MCP contains rules from several families — injection, supply chain, community — and a single family like prompt injection appears in multiple categories.

## How are the rule families organized?

The families map onto the five sub-scores. Injection, obfuscation, dangerous-shell, and supply-chain-integrity rules feed the Security or Supply Chain axes; transparency, maintenance, and community rules feed their namesake axes. Each rule names its sub-score in frontmatter, so a finding's category badge and its score contribution are always consistent. See [the five sub-scores](/docs/security-and-methodology/5-sub-scores/) for how those axes are weighted.

### Prompt injection

Prompt-injection rules catch instructions hidden in content the agent reads as trusted — a skill body, an MCP tool description, a rules file. Real examples:

- `SS-SKILL-INJECT-FENCED-RUN-01` (high) — a fenced code block carrying an imperative that tells the agent to run a command.
- `SS-MCP-POISON-UNICODE-TAG-01` (critical) — invisible plane-14 Unicode tag characters smuggled into a tool description, visible to the model and invisible to a human reviewer.
- `SS-RULES-INJECT-IMPERATIVE-01` (medium) — a rules file that commands the agent to hide or withhold information across every session.

This family is weighted heavily because indirect prompt injection is the [#1 LLM risk in OWASP's 2025 ranking (LLM01:2025)](https://genai.owasp.org/llmrisk/llm01-prompt-injection/) — and a skill body or tool description is exactly the untrusted external content it arrives in.

### Obfuscation

Obfuscation rules catch content engineered to hide its real behavior from a reviewer. `SS-HOOKS-OBFUSCATION-B64-SHELL-01` (high) fires when a hook Base64-decodes a blob and pipes it into a shell — there is no legitimate reason for a hook to obscure its own plain text. Related rules in this family catch homoglyph substitution, zero-width characters, and bidirectional-override tricks.

### Dangerous shell and remote code execution

These rules catch commands that execute attacker-controllable code, especially in hooks that run automatically on an agent event with no human in the loop. `SS-HOOKS-RCE-CURL-PIPE-01` (critical) fires when a hook pipes a remote script straight into a shell — if the URL is ever compromised, attacker code runs on your machine. The family also covers unattended `sudo`, wide `chmod`, and `rm -rf` patterns.

MCP tool poisoning is a documented variant of this threat: Invariant Labs' [Tool Poisoning Attack](https://invariantlabs.ai/blog/mcp-security-notification-tool-poisoning-attacks) (2025) demonstrated a poisoned MCP tool description that exfiltrated a user's `~/.cursor/mcp.json` and SSH keys, and OWASP lists [MCP03:2025 Tool Poisoning](https://owasp.org/www-project-mcp-top-10/) in its MCP Top 10.

### Supply chain

Supply-chain rules catch threats to provenance and integrity. `SS-MCP-SUPPLY-CHAIN-TYPOSQUAT-01` (high) flags a name one character off an established server; `SS-MCP-SUPPLY-CHAIN-HASH-DRIFT-01` (high) flags content that changed since the last scan with no CHANGELOG — the rug-pull signature; `SS-MCP-SUPPLY-CHAIN-UNSIGNED-01` (medium) flags a release with no signature to verify the bytes. The scale behind these rules is large: Sonatype's [2024 supply-chain report](https://www.sonatype.com/state-of-the-software-supply-chain/introduction) found a 156% year-over-year rise in malicious open-source packages.

### Transparency

Transparency rules are file-presence checks for the documents that let you verify what an artifact is and on what terms. `SS-SKILL-TRANSPARENCY-LICENSE-01` (medium) fires when no LICENSE file is found; companion rules check for a README, CHANGELOG, SECURITY.md, and a manifest. These are deterministic and unambiguous — a file is present or it is not.

### Maintenance

Maintenance rules use repository-history signals to judge whether a project is actively cared for. `SS-SKILL-MAINTENANCE-COMMIT-RECENCY-01` (medium) fires when the default branch has had no commit in over 365 days; companion rules check commit frequency, issue-response time, and CI health. Stale code accumulates unpatched vulnerabilities, so these are durability signals rather than security verdicts.

### Community

Community rules surface external adoption context — and most are advisory. `SS-SKILL-COMMUNITY-STARS-01` is `info`-tier (weight 0): it shows "fewer than 10 stars" as context but never moves the score, because stars are an easily-manipulated proxy for adoption. Cross-registry presence and contributor-count rules round out the family.

## Where can I see every rule?

The categories and families above are a map, not the territory. The complete, searchable list — every rule's severity, sub-score, status, framework badges, trigger logic, and limitations, rendered live at the current `rubric_version` — lives on the [methodology page](/methodology) on the main site, which also exports the visible rules to CSV. To understand how each finding is constructed and traced once a rule fires, read [finding evidence](/docs/security-and-methodology/finding-evidence/).

**Author:** SaferSkills Team — methodology maintainers.
