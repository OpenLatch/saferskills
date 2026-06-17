---
title: "FAQ"
description: "How SaferSkills scoring works and whether you can trust it, reading a score, false positives, vendor reply, and Agent Scan."
updated: 2026-06-16
author: "SaferSkills Team"
---
This page answers the questions developers ask most about SaferSkills scores: how a score is calculated, how to read it, what happens when a finding is wrong, how the behavioral Agent Scan grades a running agent, and why a low-scoring capability stays in the catalog. The short version: every verdict is **deterministic, documented, and reproducible** — there is no LLM in the verdict path — and SaferSkills publishes methodology, not endorsements.

## How does scoring work, and can I trust it?

A score is a deterministic, weighted sum of five sub-scores, with no model and no randomness anywhere in the verdict path. Each scanned capability earns a Security (35%), Supply Chain (20%), Maintenance (15%), Transparency (15%), and Community (15%) sub-score; every finding subtracts a fixed penalty (`info 0 · low 5 · medium 12 · high 25 · critical 40`); a sub-score is `max(0, 100 − Σ penalties)`. The aggregate is `round(0.35·security + 0.20·supply + 0.15·maintenance + 0.15·transparency + 0.15·community)`, then bounded by a severity ceiling: one active critical caps the whole aggregate at ≤15, one active high at ≤45.

You can trust it because you can re-derive it. Every scan stamps a `rubric_version` (the git SHA of the rule set), an `engine_version`, and a `ref_sha` (the scanned commit, or a content hash for uploads). Check those out, re-run the scan offline, and you get the same number byte-for-byte — no seed, no temperature, no [LLM](/docs/concepts/glossary/#llm) deciding the verdict. The full math, including the [five sub-scores](/docs/security-and-methodology/5-sub-scores/) and the [severity ceiling](/docs/security-and-methodology/how-scoring-works/), renders on every public report.

## How do I read a score — does a green score mean it's safe?

Read the score as a position on a four-band ladder, not a safety stamp. Green (≥80) means *Approved*, Yellow (60–79) means *Watch*, Orange (40–59) means *Caution*, and Red (0–39) means *Block*. A high score means the deterministic rule set found nothing serious at the scanned commit and the supporting signals (maintenance, transparency, community) are healthy — it does **not** certify the capability as safe, and it cannot see logic gated on a future date or content fetched at runtime. The [limitations](/docs/security-and-methodology/how-scoring-works/) of each rule are published; SaferSkills states what it cannot catch.

Practically: open the [scan report](/docs/find-and-verify/read-a-scan-report/), read the per-finding evidence — each one names the `rule_id` that fired, the matched line, why it matters, and how to fix it — and judge the capability against your own threat model. A green score lowers the cost of review; it does not replace it.

## What if a finding is a false positive — can the author respond?

Yes — every verdict is appealable, and findings are never silently deleted. A maintainer of a scanned GitHub repo proves ownership (by committing a `.saferskills/verify.txt` file with their GitHub username, or by a maintainer-email match) and then posts a public reply on the catalog item. A verified appeal triggers a re-scan with a **one-hour response SLA**; if a rule was misapplied the finding is annotated with the appeal outcome (upheld, overturned, or rule-changed), not erased — transparency over erasure. Uploaded artifacts have no repo to verify, so they carry no right-of-reply; unlisted uploads self-delete and auto-expire after 90 days instead. The full flow is in [disputing findings](/docs/for-authors/disputing-findings/).

False-positive risk is also managed before a rule ever affects a score: new rules ship in a *shadow* state where they record findings but carry zero weight, and they only go active after passing a false-positive audit. See [contribute a rule](/docs/security-and-methodology/contribute-a-rule/).

## Does Agent Scan grade itself, and how is it different from a component scan?

Agent Scan does not self-grade — the agent under test never reports its own verdict. The CLI mints a run, derives a per-run secret canary, verifies the Ed25519-signed test pack before doing anything, prints a bootstrap prompt you paste into your agent, then submits the agent's responses; the cloud **re-derives the canary deterministically and grades the evidence**, with no LLM in the verdict path. Identical evidence at the same pack version always produces the same verdict.

The difference is *behavioral versus static*. A [component scan](/docs/concepts/how-scoring-works/) reads files — a skill body, an MCP tool description, a hook command — and scores what they *contain*. An [Agent Scan](/docs/agent-scan/what-agent-scan-is/) probes how a whole running agent *behaves* against the `AS-NN` test pack, using mock tools with zero real side effects. It reuses the exact same penalty model, severity ceiling, and color bands as the component scan, so the two reports read identically. Verdicts use observation language — "observed vulnerable" or "not observed under pack v<version>", never "secure" or "certified" — and a separate [confidence](/docs/agent-scan/behavioral-scoring/) signal (high / medium / low) reflects how many optional capabilities were present without ever changing the score.

## Why is a low-scoring capability still listed in the catalog?

Because SaferSkills is a transparent public record, not a gatekeeper. A low score means *review before use*, not *banned* — the catalog publishes methodology, not endorsements, and it never tells you which capability to pick. Removing low-scoring items would hide exactly the information a developer needs: the score, the findings, the evidence, and the permalink a vendor can dispute. A red verdict is most useful when it stays visible next to its full rule trace. SaferSkills is **anti-recommendation by design** — it gives you a reproducible verdict and the reasoning behind it, and leaves the decision with you. The install CLI does add a per-user score gate (it refuses to install below a configurable minimum), but that is your choice to set, not a catalog-wide removal.

## Where do I go next?

- Start here: [what is SaferSkills](/docs/getting-started/what-is-saferskills/) · [why scanning matters](/docs/getting-started/why-scanning-matters/)
- The deep methodology: [how scoring works](/docs/security-and-methodology/how-scoring-works/) · [detection categories](/docs/security-and-methodology/detection-categories/)
- Behavioral testing: [what Agent Scan is](/docs/agent-scan/what-agent-scan-is/) · [Agent Scan FAQ](/docs/agent-scan/faq-agent-scan/)
- The API and term definitions: [API reference](/docs/reference/api/) · [glossary](/docs/concepts/glossary/)

**Author:** SaferSkills Team — methodology maintainers.
