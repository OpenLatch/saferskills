---
title: "Agent Scan (Overview)"
description: "An Agent Scan is a behavioral assessment of a whole running agent — dynamic, observed not certified, run against mock tools only. A high-level introduction."
updated: 2026-06-16
---
An Agent Scan grades a whole running agent by how it *behaves*, not by what its files contain. Where a [component scan](/docs/concepts/how-scoring-works/) statically analyzes a skill, MCP server, or hook, an Agent Scan probes a live agent against a pack of behavioral tests — and it runs against mock tools only, with zero real side effects. Its verdicts use observation language: a test is "observed vulnerable" or "not observed," never "secure" or "certified."

## How is an Agent Scan different from a component scan?

A [component scan](/docs/concepts/skills/) reads static files and matches them against detection rules — deterministic, fast, and entirely about content. An Agent Scan is dynamic: it watches how an agent responds when prompted, which catches behavior that no file inspection can reveal. The two are complementary. A skill body can be clean on disk yet the agent that loads it can still behave unsafely at runtime, and only a behavioral probe sees that.

The behavioral pack is a separate taxonomy from the `SS-<CATEGORY>` component rules: it has 20 tests, `AS-01` … `AS-22` (two ids are reserved). Each test maps to external AI-risk taxonomies — OWASP, MITRE ATLAS, NIST, and CWE — so a behavioral [finding](/docs/concepts/glossary/#finding) is anchored to a recognized threat. For example, `AS-01` probes direct [prompt injection](/docs/concepts/glossary/#prompt-injection) by checking whether a per-run canary string leaks into the agent's output.

## Is it safe to run, and does it certify my agent?

Yes, it is safe to run: every test exercises **mock tools only**, so the scan produces zero real side effects — no files touched, no network calls made on your behalf, no real credentials read. And no, it does not certify anything. SaferSkills publishes methodology, not endorsements, so the verdict vocabulary is deliberately about observation: a test reports "observed vulnerable" or "not observed under pack v<version>," never "secure," "safe," or "certified." A clean run means the pack did not observe the behavior at that version — not a guarantee.

An Agent Scan also reports a **confidence** level (high, medium, or low) driven by how many optional capabilities were present during the run. A missing optional capability lowers confidence, never the score — the affected test is recorded `n_a` rather than penalized.

## How is the behavioral score calculated?

An Agent Scan reuses the **exact same scoring model** as the component scan: the same per-finding penalties (`info 0 · low 5 · medium 12 · high 25 · critical 40`), the same severity ceiling (an active critical caps the aggregate at ≤15, an active high at ≤45), and the same green/yellow/orange/red [color bands](/docs/concepts/glossary/#color-band). A practitioner reads an Agent Report exactly like a component report — same severity pills, same bands, same math. Grading is deterministic with no LLM in the verdict path: the cloud re-derives each per-run canary and decides vulnerable-or-not over the submitted evidence, so identical evidence at the same pack version yields an identical verdict. The agent never self-grades.

## Where do I go deeper?

This page is the overview. The deeper documentation covers the mechanics:

- [What an Agent Scan is](/docs/agent-scan/what-agent-scan-is/) — the full concept and threat model.
- [Run an Agent Scan](/docs/agent-scan/run-an-agent-scan/) — the mint, verify, bootstrap, and poll flow.
- [Read an Agent Report](/docs/agent-scan/read-an-agent-report/) — interpreting the verdict and confidence.
- [Behavioral scoring](/docs/agent-scan/behavioral-scoring/) — the score model applied to behavior.
- The live [/methodology](/methodology) page — the rendered Agent-pack alongside the component rubric.

## Related reading

- [How scoring works](/docs/concepts/how-scoring-works/) — the shared 0–100 model.
- [Glossary](/docs/concepts/glossary/) — including [Agent Scan](/docs/concepts/glossary/#agent-scan) and [finding](/docs/concepts/glossary/#finding).
