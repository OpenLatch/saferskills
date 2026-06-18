---
title: "Finding Evidence"
description: "How a finding is built — rule ID, severity, explanation, remediation, a matched-line excerpt, and a rule permalink."
updated: 2026-06-16
author: "SaferSkills Team"
---
A SaferSkills finding is engineered to be self-explanatory and reproducible. It carries the firing `rule_id`, a severity, a plain-English title, an explanation of why it matters, a remediation, an optional severity rationale, and a matched-line excerpt drawn from the stored snapshot — plus a permalink to the exact rule YAML at the scanned `rubric_version`. There are no black-box findings: every one names the rule that fired and can be reproduced from its trace.

## What is in a finding?

Each finding renders a card built from the rule's documented frontmatter plus the scan's evidence. Every rule must ship the explainable-finding fields, validated against [`schemas/rubric-rule.schema.json`](https://github.com/OpenLatch/saferskills/blob/main/schemas/rubric-rule.schema.json):

- **`rule_id`** — the stable identifier, formatted `SS-<CATEGORY>-<NAME>-NN` (for example `SS-HOOKS-RCE-CURL-PIPE-01`).
- **`severity`** — one of `info`, `low`, `medium`, `high`, `critical`, rendered as a severity pill and mapped to the per-finding penalty.
- **`title`** — a plain-English headline naming what was found, with no rule_id in it.
- **`explanation`** — one or two second-person sentences on the risk and outcome class.
- **`remediation`** — an imperative `action`, optional ordered `steps`, and an optional `saferPattern` showing an "avoid this / prefer this" pair (a pattern, never a product — SaferSkills does not recommend tools).
- **`severityRationale`** — one clause tying the severity to the outcome (omitted for `info`-tier findings).
- **`limitations`** — mandatory: what the rule cannot catch. This is why there are no black-box findings.
- **`frameworks`** — optional mappings to external taxonomies (OWASP LLM Top 10, MITRE ATLAS, CWE), rendered as clickable badges.

These fields come from the rule itself, so they are identical across every artifact the rule fires on. The scan supplies the rest: where it fired and what it matched.

## What is the evidence excerpt?

The evidence excerpt is the matched-line window — the exact lines that triggered the finding — shown verbatim on the report so you see the value that was spotted, not just a description of it. It is resolved at request time from the stored artifact snapshot, the same already-public (or, for a published upload, user-published) bytes the snapshot tier already exposes. It is **not new disclosure**, and it degrades gracefully to absent when the snapshot has no bytes (a binary file, an oversized file, or an expired unlisted upload).

Crucially, the excerpt lives **only on the report response** — it is never persisted on the findings table and never written into the scan trace. That separation is deliberate and is what the next section explains.

## What does the scan trace store, and why only hashes?

The scan trace is the durable, legal-defense record of a finding, and it stores **only** structured metadata — never raw artifact payload. Per finding, the trace holds:

- `rule_id`, `severity`,
- `file_path`, `line_start` / `line_end`,
- `matched_content_sha256` — a **hash** of the matched content, not the content itself,
- a remediation link to the rule source at the recorded `rubric_version`.

The hard rule is that traces never contain skill bodies, MCP tool descriptions, or hook commands in the clear — only hashes, positions, rule IDs, and severities. If a scanned artifact contains a credential-shaped string, the finding records the rule ID, the position, and the redacted hash, never the raw secret. The trace is bounded to roughly 4 KiB per finding and 256 KiB per scan.

This matters because the trace is what a vendor uses to reproduce a verdict. A vendor must be able to re-derive a finding from the trace alone — the rule, the version, the position, the hash — without SaferSkills replaying their content back at them. The visible excerpt on the report and the hash-only trace are two separate stores with two separate contracts: one shows you the line, the other proves the finding deterministically.

## How is a finding reproducible?

Because nothing in the verdict path is probabilistic, a finding is a reproducible claim. The trace records the `rule_id` and the `rubric_version`; the rule file at that version documents the exact trigger (a regular-expression match, a file-presence check, or a metadata check); and the `matched_content_sha256` plus the `line_start`/`line_end` pin the location. Anyone can check out the rule at that `rubric_version`, run its trigger against the artifact at the recorded `ref_sha`, and confirm the same finding fires at the same line — no SaferSkills participation required.

Each finding's remediation link points at the rule's source on GitHub at the scanned version, so the trigger logic and limitations that produced the finding are always one click away. The rule's mandatory `limitations` field names what it cannot catch, so a finding is never presented as more certain than its rule actually is.

## What if I disagree with a finding?

Reproduce it first, then dispute it. Because the finding carries everything needed to re-derive it offline — rule, version, position, hash — a disagreement is a concrete, checkable argument rather than an appeal to opinion. For repositories you own, the [vendor right-of-reply](/docs/for-authors/disputing-findings/) lets you prove ownership and post a public response; a verified appeal triggers a re-scan, and findings are never silently deleted — they are annotated with the appeal outcome. For the surrounding scoring math that turns these findings into a number, see [how scoring works](/docs/security-and-methodology/how-scoring-works/); for the family each finding belongs to, see [detection categories](/docs/security-and-methodology/detection-categories/).

**Author:** SaferSkills Team — methodology maintainers.
