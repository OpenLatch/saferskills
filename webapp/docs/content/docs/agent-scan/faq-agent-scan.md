---
title: "Agent Scan FAQ"
description: "Agent Scan answered — self-administered trust, how mature it is, behavioral versus component scoring, and why a run shows pending."
updated: 2026-06-16
author: "SaferSkills Team"
---

Short answers to the questions practitioners ask most about Agent Scan: whether you can trust a score an agent runs on itself, how mature the feature is, how it differs from a component scan, and why a run sits at pending. Each question is answered in its first sentence; follow the links for the full treatment.

## Can I trust a score an agent runs on itself?

Yes — because the agent runs the tests but does not grade them. The submission an agent returns carries **no verdict field**; grading happens cloud-side, where SaferSkills re-derives the per-run canary deterministically and matches it against the evidence. A vendor can run an Agent Scan on their own agent and still cannot decide its own result, which is the whole point of the split. See [what Agent Scan is](/docs/agent-scan/what-agent-scan-is/) for why this matters.

## How mature is Agent Scan?

Agent Scan is a young, behavioral layer that complements the static component scan, and you should read its verdicts as observations, not certifications. The pack ships ~20 tests (`AS-01` … `AS-22`, with two ids reserved) anchored to OWASP Agentic, the OWASP LLM Top 10, MITRE ATLAS, and NIST. A clean run reports "not observed under pack v\<version\>" — it cannot prove the absence of behaviors the pack does not test. Treat a high score as a posture to build on, not a guarantee, and re-run as the pack grows.

## What's the difference between Agent Scan and a component scan?

A component scan reads files; an Agent Scan watches behavior. The [component scan](/docs/security-and-methodology/how-scoring-works/) statically scores a Skill, MCP server, hook, plugin, or rules artifact against deterministic `rule_id` detectors. Agent Scan drives a *running* agent through adversarial tests against mock tools and grades how it responds. They answer different questions — "is this artifact safe to install" versus "does this agent resist attack" — and share the same scoring math. See [behavioral scoring](/docs/agent-scan/behavioral-scoring/).

## Does the scan do anything to my system?

No — every test runs against mock tools only, with zero real side effects. Tools the tests need (file reads, destructive actions, finance relays) are mocked: the pack records that the agent *tried* to call them without performing the action. Secret-disclosure tests plant a per-run honeytoken, never a real credential. Nothing on your machine is read, written, sent, or deleted.

## Why is my scan pending?

A run sits at pending while your agent is still working through the pack — the setup is quick, but the agent's own test run takes longer. After the CLI mints the run, verifies the signed pack, and prints the bootstrap prompt, your agent runs ~20 tests and submits evidence; a real run commonly takes 10–40 minutes. The CLI polls and waits up to the `--timeout` value (default 45 minutes); once evidence is submitted, the cloud grades it and the verdict appears. See [Run an Agent Scan](/docs/agent-scan/run-an-agent-scan/) for the full flow.

## What does a "confidence" label mean on my report?

Confidence reports how much of the pack could run, not how safe the agent is. A missing optional capability records the affected test as `n_a` and lowers *confidence* — it never changes the score. Read the score and confidence together: a high score at low confidence means few tests were exercised. Details in [behavioral scoring](/docs/agent-scan/behavioral-scoring/).

**Author:** SaferSkills Team — methodology maintainers.
