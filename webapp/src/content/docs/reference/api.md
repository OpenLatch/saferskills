---
title: "API (Experimental)"
description: "The few real public SaferSkills endpoints — scan submit and list, item lookup, badge SVG, agent-scans, stats — with no stability guarantee."
updated: 2026-06-16
---
SaferSkills exposes a small public HTTP API under `/api/v1` for submitting scans, reading reports, browsing the catalog, fetching a badge, and running an Agent Scan. It is **experimental and carries no stability guarantee** — paths, fields, and shapes can change without notice or a version bump. All JSON bodies use **snake_case** keys, and every paginated list returns its rows under a `data` array. Build against it knowing it may move.

## Is the API stable?

No. Treat the API as experimental — there is no public stability contract at this stage, no semantic versioning of the endpoints, and no deprecation window. Field names, status codes, and pagination shapes can change between releases. For anything you need to rely on, prefer the [`saferskills` CLI](/docs/install/cli-reference/) (which absorbs API churn behind real commands) or the live web surfaces at [saferskills.ai](https://saferskills.ai). If you do call the API directly, pin nothing and expect drift.

## What conventions does every response follow?

Two conventions hold across the whole surface. Request and response JSON bodies use **snake_case** keys (`rubric_version`, `repo_aggregate_score`, `ref_sha`) — never camelCase — and every paginated list response puts its items under a top-level `data` array, never `items`. Lists also carry pagination metadata (a cursor and a total count) alongside `data`. Scores are integers from 0 to 100, severities are one of `info / low / medium / high / critical`, and tiers map to the [color bands](/docs/security-and-methodology/how-scoring-works/) Green / Yellow / Orange / Red.

## What endpoints exist for scanning a repo?

Scanning lives under `/api/v1/scans`. You submit a public GitHub URL, the engine runs a [deterministic scan](/docs/concepts/how-scoring-works/), and you read the report back.

| Method & path | What it does |
|---|---|
| `POST /api/v1/scans` | Submit a public GitHub URL for scanning. Anti-abuse gated (a human-verification token plus a per-IP daily cap; loopback callers exempt). Returns `202 Accepted` with the run id. |
| `POST /api/v1/scans/upload` | Submit an uploaded artifact (multipart — one file, a `.zip`, or several loose files) for scanning. |
| `GET /api/v1/scans` | List recent public repo scan runs (one row per repo, not per capability). Supports `tier`, `order`, and a `cursor`. |
| `GET /api/v1/scans/runs/{run_id}` | Read the full repo scan report — every capability discovered, each with its own score and findings. |
| `GET /api/v1/scans/{scan_id}` | Read the report for a single capability scan. |
| `GET /api/v1/scans/{run_id}/events` | Server-Sent Events progress stream for an in-flight run. |

Unlisted (private) scans are reached only through an unguessable `share_token`: `GET /api/v1/scans/r/{token}` reads it, `POST /api/v1/scans/r/{token}/promote` makes it public (one-way), `DELETE /api/v1/scans/r/{token}` removes it, and `GET /api/v1/scans/r/{token}/download` returns its bytes as a `.zip`. Invalid, expired, or non-unlisted tokens all return a generic `404` — there is no oracle distinguishing them.

```bash
# Submit a repo (requires a human-verification token header in production)
curl -X POST https://saferskills.ai/api/v1/scans \
  -H "content-type: application/json" \
  -d '{"github_url": "https://github.com/acme/devtools-agent-kit"}'

# Read the run report
curl https://saferskills.ai/api/v1/scans/runs/<run_id>
```

For the human-facing versions of these flows, see [scan a repo](/docs/find-and-verify/scan-a-repo/) and [read a scan report](/docs/find-and-verify/read-a-scan-report/).

## How do I look up a catalog item and its score?

The catalog lives under `/api/v1/items`. `GET /api/v1/items` lists catalog entries (the `data` array) and accepts filters — `kind`, `agent`, scan-tier, `min-score`, and an `artifact_source` of `github` or `upload` — plus sort keys such as `most_installed`, `recent`, `highest_score`, `most_starred`, `name_asc`, and `most_active`. `GET /api/v1/items/{slug}` returns one capability's full detail: its current score, sub-score breakdown, findings, and version history. One catalog entry is one capability, so a multi-capability repo produces several item slugs.

```bash
# Highest-scoring skills, scoped to one agent
curl "https://saferskills.ai/api/v1/items?kind=skill&agent=claude-code&order=highest_score"

# One capability's report
curl https://saferskills.ai/api/v1/items/acme--devtools-agent-kit--skill-pdf-extract
```

A verified maintainer can post a [right-of-reply](/docs/for-authors/disputing-findings/) to a scanned GitHub repo via `POST /api/v1/items/{slug}/vendor/responses` (ownership is proven first through the vendor-verify endpoints under the same `/items/{slug}/vendor/` prefix).

## How do I get a badge SVG?

A scan-result badge is served as a static SVG at `https://saferskills.ai/badge/{scan_id}/{score}.svg`. Embed it in a README with the catalog item as the link target. A forged score in the URL is rejected, so the badge always reflects the real verdict. Full instructions are in [embed your badge](/docs/find-and-verify/embed-your-badge/).

```markdown
[![SaferSkills 92/100](https://saferskills.ai/badge/<scan_id>/<score>.svg)](https://saferskills.ai/items/<slug>)
```

## What other endpoints are public?

A few support endpoints round out the surface:

- `GET /api/v1/health` — liveness check.
- `GET /api/v1/stats` — platform metrics used by the homepage.
- `GET /api/v1/agent-scans` and `POST /api/v1/agent-scans` — list and start a behavioral [Agent Scan](/docs/agent-scan/what-agent-scan-is/); `GET /api/v1/agent-scans/{run_id}` reads a public Agent Report, and `GET /api/v1/agent-scans/aggregate-stats` returns corpus aggregates. The public Agent Report projection never includes the raw submitted transcript.
- `GET /api/v1/installs` and `POST /api/v1/installs` — the CLI's anonymous, opt-in install-count reporting (closed-enum agent and kind only, no slug, redacted IP).

Endpoints under `/api/v1/admin/*` and the GitHub webhook intake are operator-only and not part of the public surface.

## Where do I go next?

- Up: [Reference](/docs/reference/about/) · [FAQ](/docs/reference/faq/)
- The CLI that wraps these flows: [CLI reference](/docs/install/cli-reference/)
- How a score is computed: [how scoring works](/docs/security-and-methodology/how-scoring-works/)
- Term definitions: [glossary](/docs/concepts/glossary/)
