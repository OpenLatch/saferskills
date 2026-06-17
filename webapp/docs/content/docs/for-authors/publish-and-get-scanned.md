---
title: "Publish & Get Scanned"
description: "Submit a public GitHub URL and SaferSkills indexes and scans it in about 30 seconds — the result is a public report."
updated: 2026-06-16
---
To get your capability indexed and scanned, submit its public GitHub URL at [/scan](/scan). SaferSkills walks the repo, discovers every capability it holds, and scores each one against the rule corpus in about 30 seconds. The scan is deterministic — no model, no opinion — and the result is a public report with a permalink, a full rule trace, and a vendor right-of-reply.

## How do I get my repo scanned?

Paste the repository URL into the [scan page](/scan), or call the API directly. The form accepts `https://github.com/<owner>/<repo>` (and sub-trees). One submission scans the whole repo: SaferSkills [discovers each capability](/docs/concepts/skills/) — a Skill, an [MCP server](/docs/concepts/mcp-servers/), [hooks](/docs/concepts/hooks/), a rules set — and scores it independently, then rolls those up into a consolidated repo score (the mean of the per-capability scores). Each capability becomes its own catalog entry at `/items/<slug>` with version history and a permalink.

The same engine accepts a direct upload at [/scan](/scan) if you do not have a public repo to point at. Uploaded artifacts have no upstream owner, so they have **no vendor right-of-reply** — see [Claim your repo](/docs/for-authors/claim-your-repo/) for why that matters and what to use instead.

You can also submit programmatically with `POST /api/v1/scans` (a GitHub URL) or `POST /api/v1/scans/upload` (multipart). Both pass through a human-verification gate and a per-IP daily cap. See the [API reference](/docs/reference/api/).

## What does the scan check?

The scan produces five sub-scores, each weighted into one aggregate from 0 to 100:

| Sub-score | Weight | What it catches |
|---|---:|---|
| **Security** | 35% | [Prompt injection](/docs/concepts/glossary/#prompt-injection), obfuscation, dangerous shell, credential exfiltration |
| **Supply Chain** | 20% | Typosquat, owner-transfer, hash drift, unsigned releases |
| **Maintenance** | 15% | Commit recency, commit frequency, issue-response time, CI health |
| **Transparency** | 15% | LICENSE / README / CHANGELOG / SECURITY.md / manifest presence |
| **Community** | 15% | Stars, contributors, cross-registry presence, fork health |

The aggregate is `round(0.35·security + 0.20·supply + 0.15·maintenance + 0.15·transparency + 0.15·community)`. Because Security is only 35% of the weight, a serious finding cannot be diluted by good docs: one active **critical** finding caps the whole aggregate at ≤15, and one active **high** caps it at ≤45. For the exact math, read [How scoring works](/docs/security-and-methodology/how-scoring-works/) and the [five sub-scores](/docs/security-and-methodology/5-sub-scores/). To shape your repo so it scores well, see the [SKILL.md spec](/docs/for-authors/skill-md-spec/).

## How long does it take, and what do I get?

A scan takes roughly 30 seconds. You can watch progress over Server-Sent Events while it runs, then you land on the public report. Every report renders the explicit penalty-by-penalty math, the per-finding evidence, and the stamped `rubric_version`, `engine_version`, and `ref_sha` — so you (or anyone) can re-derive the verdict offline against the same bytes and the same rules. Nothing about the verdict is hidden or probabilistic. Learn to read the output in [Read a scan report](/docs/find-and-verify/read-a-scan-report/).

## Is the result public?

Yes. A scan of a public GitHub repo produces a public catalog entry indexed at `/items/<slug>` and listed in the [catalog](/catalog). The score, findings, rule trace, and version history are all public, by design — transparency is the product. A low score is not a verdict against your work; it means *review before use*, and you can respond to it directly through the [right-of-reply](/docs/for-authors/claim-your-repo/) if you believe a finding is wrong.

Once you have a score you are happy with, embed the live badge in your README so installers see the current grade at a glance. See [Embed your badge](/docs/find-and-verify/embed-your-badge/).

## Where do I go next?

- [SKILL.md spec](/docs/for-authors/skill-md-spec/) — author a repo that scores well
- [How scoring works](/docs/security-and-methodology/how-scoring-works/) — the deterministic scoring model
- [Embed your badge](/docs/find-and-verify/embed-your-badge/) — publish your live score
- [Claim your repo](/docs/for-authors/claim-your-repo/) — prove ownership and respond to findings
