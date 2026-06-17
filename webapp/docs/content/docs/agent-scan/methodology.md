---
title: "Agent Scan Methodology"
description: "How SaferSkills grades agents — a bridge to the live /methodology page (OWASP Agentic, OWASP LLM Top 10, MITRE ATLAS), not re-authored here."
updated: 2026-06-16
author: "SaferSkills Team"
---

SaferSkills grades agents with a documented behavioral test pack, and the single source of truth for that pack is the live [methodology page](/methodology) — auto-rendered from the rubric, never hand-copied. Each of the ~20 tests (`AS-01` … `AS-22`, with two ids reserved) is anchored to a recognized threat taxonomy: OWASP Agentic Security Initiative (`ASI…:2026`), the OWASP LLM Top 10 (`LLM…:2025`), MITRE ATLAS, and NIST AI 600-1. This page is a bridge; the pack itself is not re-authored here.

## Where is the authoritative pack?

On the live [methodology page](/methodology), under the Agent-pack section. That page is generated directly from the rubric, so the test list, severities, framework badges, and detection logic shown there are always current with what the engine actually runs. Re-stating the pack in these docs would risk drift, so we point at the rendered source instead of copying it.

## What threat frameworks does the pack map to?

Every behavioral test references at least one external AI-risk taxonomy, so a finding is anchored to a recognized threat rather than an opaque opinion. The pack maps tests to OWASP's Agentic Security Initiative ids (for example `ASI01:2026`), the OWASP Top 10 for LLM Applications (for example `LLM01:2025`, which ranks [Prompt Injection](/docs/concepts/glossary/#prompt-injection) as the top risk — [source](https://genai.owasp.org/llmrisk/llm01-prompt-injection/)), MITRE ATLAS techniques, and NIST AI 600-1. The methodology page renders these as clickable badges on each test card.

## How are agents actually graded?

Grading reuses the component scoring model and stays deterministic. The cloud re-derives each per-run canary, decides each test's verdict over the submitted evidence, and applies the same penalties, the same severity ceiling, and the same color bands a component scan uses — there is no LLM in the verdict path. For the scoring math, see [behavioral scoring](/docs/agent-scan/behavioral-scoring/); for the conceptual frame, see [what Agent Scan is](/docs/agent-scan/what-agent-scan-is/).

## Where do I go next?

Read the full, rendered pack on the live [methodology page](/methodology). To understand the resulting number, see [how behavioral scoring works](/docs/agent-scan/behavioral-scoring/).

**Author:** SaferSkills Team — methodology maintainers.
