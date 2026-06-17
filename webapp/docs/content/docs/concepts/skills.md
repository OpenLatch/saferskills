---
title: "Skills"
description: "A skill is a bundled capability that extends an agent with functions it calls at runtime — here is its security surface and how SaferSkills scores one."
updated: 2026-06-16
---
A skill is a bundled capability — typically a `SKILL.md` file plus supporting assets — that extends an agent with functions, instructions, or workflows it loads and calls at runtime. Because the agent reads a skill body as trusted instructions, that body is a security surface: it can carry prompt injection, request credential access, or instruct the agent to run shell commands. SaferSkills scans skills fully in v1.

## What is a skill?

A skill packages a unit of agent capability so it can be installed, shared, and invoked on demand. In the Claude Skills format the anchor is a `SKILL.md` file in a `skills/` directory; the agent loads that body as part of its working context and follows its instructions when the skill is active. A skill can also ship templates, scripts, and reference material the agent draws on while the skill runs.

Skills are the most widely supported [capability](/docs/concepts/glossary/#capability) kind. The agents that natively load a `skills/` directory include Claude Code, OpenAI Codex, GitHub Copilot, Gemini, and OpenClaw. See [Install a skill](/docs/install/install-a-skill/) for the per-agent install paths.

## What is the security surface of a skill?

A skill is risky precisely because the agent trusts its body. The same body that tells the agent how to do useful work can tell it to do something harmful, and three classes of risk recur:

- **Injection in the body.** A skill body is untrusted external content the model reads, which is the textbook setting for [prompt injection](/docs/concepts/glossary/#prompt-injection) — ranked the top risk in the [OWASP Top 10 for LLM Applications (2025)](https://genai.owasp.org/llmrisk/llm01-prompt-injection/). Injection can hide in plain imperatives ("ignore previous instructions"), in invisible Unicode tag-channel characters, or in homoglyph-swapped text the reader cannot see.
- **Credential access.** A skill can instruct the agent to read `~/.aws/credentials`, an `~/.ssh/id_*` private key, environment variables, or a GitHub token — then act on or exfiltrate what it finds.
- **Shell execution.** A skill can embed a fenced code block that reads as a "run this" imperative, turning a documentation snippet into an executed command on your machine.

These are not hypothetical categories: SaferSkills ships detection rules for each, including `SS-SKILL-INJECT-FENCED-RUN-01` (a fenced run-this imperative, `high`, security) and `SS-SKILL-INJECT-UNICODE-TAG-01` (invisible Unicode tag-channel injection). Browse the full set on the [live methodology page](/methodology).

## How does SaferSkills score a skill?

SaferSkills runs a deterministic static scan and produces a 0–100 [aggregate score](/docs/concepts/glossary/#aggregate-score) from five weighted [sub-scores](/docs/concepts/glossary/#sub-score) — Security (35%), Supply Chain (20%), Maintenance (15%), Transparency (15%), and Community (15%). Each [finding](/docs/concepts/glossary/#finding) carries a static [`rule_id`](/docs/concepts/glossary/#rule_id) and a quotable line of evidence; there is no LLM in the verdict path, so the same skill bytes always yield the same score.

An active `critical` finding caps the whole aggregate at ≤15, and an active `high` caps it at ≤45 — so a serious skill-body flaw can never be diluted by clean docs or a healthy star count. A low score is an instruction to **review before use**, not a verdict that the skill is unusable. For the full breakdown, read [How scoring works](/docs/concepts/how-scoring-works/).

## Where do I go next?

- [How scoring works](/docs/concepts/how-scoring-works/) — the score model in one page.
- [Install a skill](/docs/install/install-a-skill/) — per-agent install paths for all eight supported agents.
- [Glossary](/docs/concepts/glossary/) — definitions for every term above.
