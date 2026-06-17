---
title: "About"
description: "What SaferSkills is — a free, open-source, deterministic trust-scoring service for AI capabilities — and who stewards it."
updated: 2026-06-16
---
SaferSkills is a public, free, Apache-2.0 service that independently scans every AI capability — skills, MCP servers, hooks, plugins, and rules — across every agent platform. Anyone submits a GitHub URL or uploads files, a deterministic scan runs in about thirty seconds, and the result is a public report: a 0–100 trust score, a full rule trace, a quotable line of evidence per finding, a vendor right-of-reply, and a permanent permalink. No LLM sits in the verdict path.

## What does SaferSkills actually do?

It scans AI capabilities and publishes the result as a transparent, reproducible record. The engine walks a repository, discovers each capability, and scores it independently against a documented rule set across five sub-scores — Security, Supply Chain, Maintenance, Transparency, and Community. Beyond these static [component scans](/docs/concepts/how-scoring-works/), SaferSkills also runs a behavioral [Agent Scan](/docs/agent-scan/what-agent-scan-is/) that grades how a whole running agent behaves against a test pack. Everything is deterministic: the same input always produces the same score, and a vendor can re-derive any historical verdict offline.

## What does SaferSkills stand for?

Three principles shape every page and every verdict. **Methodology over opinion** — each rule is published, each score shows its math, and "we score X by rule Y" replaces "X is bad." **Anti-recommendation** — SaferSkills never tells you which capability to use; a low score means *review before use*, not *don't use*. **Transparency over erasure** — findings are appealable through a [vendor right-of-reply](/docs/for-authors/disputing-findings/) but never silently deleted, so the public record stays honest.

## Who stewards SaferSkills?

SaferSkills is an OpenLatch project, run brand-independently. The code is open source under the Apache License 2.0, the methodology is contributed and disputed in public, and the live service runs at [saferskills.ai](https://saferskills.ai). The source, the rule corpus, and the contribution and appeal templates all live in the public repository at [github.com/OpenLatch/saferskills](https://github.com/OpenLatch/saferskills).

## Where do I go next?

- New here: [what is SaferSkills](/docs/getting-started/what-is-saferskills/) · [why scanning matters](/docs/getting-started/why-scanning-matters/)
- Common questions: [FAQ](/docs/reference/faq/)
- The public API: [API reference](/docs/reference/api/)
