---
title: "How Scoring Works (Overview)"
description: "A SaferSkills score is a deterministic 0–100 number from five weighted sub-scores, bucketed into four color bands — here is the overview."
author: "SaferSkills Team"
updated: 2026-06-16
---
A SaferSkills score is a single 0–100 number computed deterministically from five weighted sub-scores, then bucketed into one of four color bands. It is methodology, not opinion: every point of penalty traces to a documented rule and a quotable line of evidence, with no LLM in the verdict path. This page is the overview; the [full methodology](/docs/security-and-methodology/how-scoring-works/) carries the exact math.

## What are the five sub-scores?

Every scan produces five [sub-scores](/docs/concepts/glossary/#sub-score), each scored 0–100, then combined by a fixed weighted sum:

| Sub-score | Weight | What it catches |
|---|---:|---|
| **Security** | 35% | Prompt injection, obfuscation, dangerous shell, credential exfiltration |
| **Supply Chain** | 20% | Typosquat, owner-transfer, hash drift, unsigned releases |
| **Maintenance** | 15% | Commit recency, commit frequency, issue-response time, CI health |
| **Transparency** | 15% | LICENSE / README / CHANGELOG / SECURITY.md / manifest presence |
| **Community** | 15% | Stars, contributors, cross-registry presence, fork health |

Security carries the most weight because it catches the threats that actually compromise a machine — but the weight alone does not let security dominate, which the severity ceiling (below) corrects.

## How is the aggregate calculated?

Each [finding](/docs/concepts/glossary/#finding) carries a [severity tier](/docs/concepts/glossary/#severity-tier) with a fixed penalty: `info 0 · low 5 · medium 12 · high 25 · critical 40`. A sub-score is `max(0, 100 − Σ penalties)`. The [aggregate score](/docs/concepts/glossary/#aggregate-score) is the rounded weighted sum:

```text
aggregate = round(0.35·security + 0.20·supply + 0.15·maintenance
                  + 0.15·transparency + 0.15·community)
```

A pure weighted sum would let a critical security flaw hide behind good docs and a healthy star count, so a **severity ceiling** caps the whole aggregate by the worst active finding: one active `critical` caps it at **≤15**, one active `high` caps it at **≤45**. This is why a serious flaw can never be diluted by the 65% of weight that sits outside Security. The exact step-by-step math — per-finding penalty, running sub-score, weighted aggregate, ceiling application — is in the [detailed methodology](/docs/security-and-methodology/how-scoring-works/), and every public report renders it inline.

## What do the color bands mean?

The aggregate buckets into four [color bands](/docs/concepts/glossary/#color-band):

| Band | Range | Label |
|---|---|---|
| **Green** | 80–100 | Approved |
| **Yellow** | 60–79 | Watch |
| **Orange** | 40–59 | Caution |
| **Red** | 0–39 | Block |

A band is a reading aid, not a verdict on you. SaferSkills publishes methodology, not endorsements: a Red score means **review the findings before use**, not "never use this." You decide; the score tells you where to look first.

## Why is it deterministic?

Same input, same score — byte-for-byte. There is no model, no random seed, and no temperature anywhere in the verdict path. Every scan stamps three identifiers: [`rubric_version`](/docs/concepts/glossary/#rubric_version) (the git SHA of the rule set), `engine_version` (the scan engine), and the [scan run](/docs/concepts/glossary/#scan-run)'s `ref_sha` (the scanned commit, or `content_hash_sha256` for an upload). A vendor can check out those exact versions and re-derive any historical verdict offline, without SaferSkills' participation. That reproducibility is what makes the [vendor right-of-reply](/docs/concepts/glossary/#right-of-reply) meaningful.

## Where do I go deeper?

- [How scoring works — the full methodology](/docs/security-and-methodology/how-scoring-works/) — the complete scoring contract.
- [The five sub-scores](/docs/security-and-methodology/5-sub-scores/) — what each axis measures and how it is penalized.
- [Detection categories](/docs/security-and-methodology/detection-categories/) — the closed set of rule categories.
- [Glossary](/docs/concepts/glossary/) — every term used above.
