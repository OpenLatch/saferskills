---
title: "The Five Sub-Scores"
description: "Security 35%, Supply Chain 20%, Maintenance, Transparency, and Community 15% each — what every axis measures and weighs."
updated: 2026-06-16
author: "SaferSkills Team"
---
Every SaferSkills score is a weighted sum of five sub-scores: Security at 35%, Supply Chain at 20%, and Maintenance, Transparency, and Community at 15% each. Each axis starts at 100, subtracts the severity penalties of the findings assigned to it, and contributes its share to the aggregate. The weights are locked by the rubric — they are never tuned per artifact.

## What are the five sub-scores and their weights?

The aggregate is a closed-form weighted sum of five axes, each a number from 0 to 100:

| Sub-score | Weight | What it catches |
|---|---:|---|
| **Security** | 35% | Prompt injection, obfuscation, dangerous shell, credential exfiltration |
| **Supply Chain** | 20% | Typosquat, owner-transfer, hash drift / rug-pull, unsigned releases |
| **Maintenance** | 15% | Commit recency, commit frequency, issue-response time, CI health |
| **Transparency** | 15% | LICENSE, README, CHANGELOG, SECURITY.md, manifest presence |
| **Community** | 15% | Stars, contributors, cross-registry presence, fork health |

Security carries more than a third of the total weight because security failures are the ones that compromise your machine; the other four axes together are the quality and trust context around the artifact. Each sub-score is computed as `max(0, 100 − Σ penalties)`, and any axis with a `critical` finding is capped at 20. The aggregate then combines them as `round(0.35·security + 0.20·supply_chain + 0.15·maintenance + 0.15·transparency + 0.15·community)`. The full math, including the severity ceiling that prevents a security failure from being diluted, is in [how scoring works](/docs/security-and-methodology/how-scoring-works/).

## What does the Security sub-score measure?

Security catches the behaviors that let an artifact act against you: prompt injection, obfuscation, dangerous shell execution, and credential exfiltration. It is the heaviest axis at 35% because these are the highest-consequence failures, and a critical Security finding triggers the aggregate severity ceiling that caps the whole score at ≤15.

Representative rule families and IDs:

- **Prompt injection** — `SS-SKILL-INJECT-FENCED-RUN-01` (high), a fenced code block carrying a natural-language imperative that tells the agent to run a command; `SS-MCP-POISON-UNICODE-TAG-01` (critical), invisible Unicode tag characters hidden in an MCP tool description.
- **Dangerous shell / remote code execution** — `SS-HOOKS-RCE-CURL-PIPE-01` (critical), a hook that pipes a remote script straight into a shell.
- **Obfuscation** — `SS-HOOKS-OBFUSCATION-B64-SHELL-01` (high), a hook that Base64-decodes a blob and runs it as shell.
- **Credential exfiltration** — `SS-PLUGIN-SECRET-EXFIL-GH-TOKEN-01` (critical), a committed GitHub token in plugin source.

This axis is why prompt injection gets disproportionate attention in the rubric. OWASP ranks [prompt injection as LLM01:2025](https://genai.owasp.org/llmrisk/llm01-prompt-injection/), the top risk in the OWASP Top 10 for LLM Applications, and a skill body or tool description is precisely the untrusted external content an indirect injection arrives in.

## What does the Supply Chain sub-score measure?

Supply Chain catches threats to the provenance and integrity of the artifact: typosquatting, owner transfers, content drift, and unsigned releases. At 20% it is the second-heaviest axis, reflecting how often a compromise arrives through the distribution channel rather than the original code.

Representative rules:

- `SS-MCP-SUPPLY-CHAIN-TYPOSQUAT-01` (high) — a name within one character of an established MCP server, the classic fat-finger trap.
- `SS-MCP-SUPPLY-CHAIN-HASH-DRIFT-01` (high) — server content changed since the last scan with no matching CHANGELOG, the rug-pull signature.
- `SS-MCP-SUPPLY-CHAIN-UNSIGNED-01` (medium) — a release shipping without any signature to tie the bytes to their maintainer.

The scale of this threat is industrial. Sonatype's [10th Annual State of the Software Supply Chain Report (2024)](https://www.sonatype.com/state-of-the-software-supply-chain/introduction) reported a 156% year-over-year increase in malicious open-source packages, with more than 704,000 identified since 2019 — the backdrop against which provenance signals matter.

## What does the Maintenance sub-score measure?

Maintenance measures whether the project is actively cared for: commit recency, commit frequency, issue-response time, and CI health. A stale, unmaintained artifact accumulates unpatched CVEs and compatibility drift, so this axis is a quality and durability signal rather than a security verdict.

A representative rule is `SS-SKILL-MAINTENANCE-COMMIT-RECENCY-01` (medium), which fires when the default branch has had no commit in more than 365 days — a marker of either abandonment or a finished project at steady state. Maintenance rules use repository-history triggers (commit ages, frequency windows, issue-response percentiles) rather than content matches.

## What does the Transparency sub-score measure?

Transparency measures whether the artifact tells you what it is and on what terms: the presence of a LICENSE, README, CHANGELOG, SECURITY.md, and a manifest. Missing transparency is rarely malicious, but it leaves you unable to verify terms, track changes, or report a vulnerability.

A representative rule is `SS-SKILL-TRANSPARENCY-LICENSE-01` (medium), which fires when no LICENSE file is found — without one, the artifact is "all rights reserved" by default, which can block redistribution and use depending on your compliance posture. Transparency rules are file-presence checks, so they are deterministic and unambiguous.

## What does the Community sub-score measure?

Community measures external adoption signals: stars, contributor count, cross-registry presence, and fork health. These are the softest signals in the rubric, easily manipulated and never proof of quality, so several of them are advisory-only.

A representative rule is `SS-SKILL-COMMUNITY-STARS-01`, which is `info`-tier and therefore carries weight 0: it surfaces "fewer than 10 stars" as context on the report but does not move the score. Treating star count as advisory is a deliberate choice — popularity is not safety, and the rubric refuses to let an easily-gamed proxy stand in for either.

## How do the sub-scores fit together?

Each axis is independent in what it measures but combined by the fixed weighting above. A clean Security axis cannot rescue a critical finding (the severity ceiling dominates), and strong Maintenance, Transparency, and Community scores cannot lift an artifact with a serious security flaw out of the Red band. To see the per-category rule families that feed each axis, read [detection categories](/docs/security-and-methodology/detection-categories/); for the precise aggregate math and bands, read [how scoring works](/docs/security-and-methodology/how-scoring-works/); and for the vocabulary used throughout, the [glossary](/docs/concepts/glossary/) defines terms like [prompt injection](/docs/concepts/glossary/#prompt-injection) and [supply chain](/docs/concepts/glossary/#sub-score).

**Author:** SaferSkills Team — methodology maintainers.
