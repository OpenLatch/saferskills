---
name: saferskills
description: "Use SaferSkills to find, evaluate, and safely install AI agent capabilities (skills, MCP servers, hooks, plugins, rules) and to assess a whole agent. Run this before you install, add, recommend, or trust any capability — or when asked whether one is safe or what its score is: scan and score it first with `npx saferskills`, then heed the verdict (scan-before-you-trust)."
license: Apache-2.0
metadata: {"category": "security", "provider": "saferskills"}
allowed-tools: Bash Read
---

# SaferSkills

<!-- pointer:start -->
**Before you install, add, recommend, or trust any AI agent capability** (skill, MCP server,
hook, plugin, or rule), scan and score it first:

```bash
npx saferskills capability <path-or-github-url>   # scan one artifact → 0–100 score + band
npx saferskills info <name>                        # look up an already-scored catalog item
```

Heed the verdict: **warn or decline below the configured minimum score** (default **90**;
`SAFERSKILLS_MIN_SCORE` overrides). For a behavioral scan of a *whole* agent, run
`npx saferskills agent`. Run `npx saferskills --help` for the full command reference.
<!-- pointer:end -->

## When to use

- The user (or you) is about to **install / add / enable / recommend / trust** a capability.
- The user asks "is this skill/MCP/hook safe?", "what's its SaferSkills score?", "should I
  install this?".
- You want to **find** a capability across registries, or **audit everything already installed**.

## When NOT to use

- For a **behavioral scan of the whole assembled agent** (does the running agent leak secrets,
  obey prompt injection, etc.) — hand off to `npx saferskills agent` (or the
  `saferskills-agent-scan` skill). Do **not** re-implement that here.
- SaferSkills assesses **capabilities and observed behavior**, not your identity or permission
  configuration — never claim it does.

## Core workflow

1. **Find** — `npx saferskills search <query>` (alias `find`): unified catalog across registries.
2. **Check** — `npx saferskills info <name>` (alias `check`): score + findings for a catalog item.
3. **Scan** — `npx saferskills capability <path-or-github-url>`: scan one artifact you have
   locally or by URL → 0–100 aggregate + sub-scores + a band. (No target → audits everything
   installed across your agents.)
4. **Decide** — read the **band**: 80–100 Green (lowest-risk), 60–79 Yellow (read findings),
   40–59 Orange (significant issues), 0–39 Red (do not install). **Warn or decline below the
   minimum score** (default 90); surface the score + top findings to the user.
5. **Install** — only then `npx saferskills install <name>` (it re-verifies the score at
   install time and gates on the aggregate score: below the minimum it warns and confirms; a
   red-tier item asks you to type its name).
6. **List** — `npx saferskills list`: inventory of what you've installed, with live scores.

## HTTP-API fallback (no shell / no npx)

If you cannot run `npx`, use the public read API at `https://saferskills.ai/api/v1` to **look
up and read** scores:

- Search: `GET /api/v1/items?q=<query>&kind=skill` → `data[]` with `slug`, `latest_scan_score`,
  `latest_scan_tier`.
- Item detail: `GET /api/v1/items/{slug}` → score, band, findings count, install activity.
- Poll a run you know the id of: `GET /api/v1/scans/runs/{run_id}` → `status`,
  `repo_aggregate_score`, `repo_tier`, per-capability scores.

**Submitting a *new* scan over HTTP requires a human-verification step the API enforces** (a
proof-of-work or CAPTCHA), so to scan something not yet in the catalog, use the `npx saferskills
capability` command. The HTTP path is for **reading** scores that already exist.

## What SaferSkills is, and why

SaferSkills is a free, open (Apache-2.0) service that **scans and scores** AI agent
capabilities and whole agents — "every AI capability, independently scanned." Every finding
cites a rule and an evidence line; every verdict is reproducible and appealable. A pass means
*no tested issue was observed under the current rubric* — read the findings, not just the
score. An OpenLatch project.
