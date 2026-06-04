# Ingestion Sources & Scraping Posture

SaferSkills indexes AI-capability artifacts (Skills, MCP servers, hooks, plugins)
from official APIs and public aggregator registries. This page documents **how** we
crawl each source, what we store, and how an operator stops a crawl.

Every adapter obeys the [ToS-respect mandates](../.claude/rules/ingestion.md#tos-respect-mandates):
declared `User-Agent: SaferSkillsBot/1.0 (+https://saferskills.ai/bot)` + `From:
bot@saferskills.ai` on every request, `robots.txt` honored before any scrape fetch,
descriptions paraphrased to ≤280 chars (never a full README/manifest body), a
back-link credited to the source listing, and the per-source rate limit declared in
the YAML config is never exceeded.

## Fetch posture (lean, no headless browser)

Aggregator adapters use a **3-tier discovery precedence** (feed → sitemap → HTML),
deliberately **without** a headless-browser tier:

| Tier | Mechanism | Transport |
|---|---|---|
| 0 | JSON feed / REST API | HTTPX (SSRF allowlist + Hishel RFC-9111 cache) |
| 0 | XML sitemap (`<loc>` extraction, XXE-safe via `defusedxml`) | HTTPX |
| 1 | Browser-impersonating HTML fetch | curl_cffi (`impersonate=chrome131`) |

A Cloudflare interstitial detected at tier 1 is **terminal**: the adapter raises
`AdapterBlockedError`, the cycle flips the source to `status='blocked'` (no retry
storm), and the eagle-eye view + the 15-min pager surface it. There is **no
Playwright/stealth-browser tier** — it was dropped to keep the deploy image small
(small Fly machines). A persistently `blocked` Cloudflare-gated source is documented
here, not force-cracked.

## Source table

| Source | Kind | Method | Status | Cadence (UTC) | Notes |
|---|---|---|---|---|---|
| `github_skills` | webhook | GitHub push webhook | active | on push | `anthropics/skills` + allies |
| `github_topics` | api | GitHub Search API (+ flagged code-search) | active | 01:00 daily | 4 topics × star shards |
| `mcp_registry` | api | Official MCP Registry `/v0/servers` | active | hourly | cursor by `updated_since` |
| `npm` | api | npm registry | active | per config | `mcp-server-*` packages |
| `pypi` | api | PyPI | active | per config | MCP/skill packages |
| `smithery` | scrape | Smithery registry API (`registry.smithery.ai/servers`) | **active (Phase B)** | 03:15 daily | feed-first; OSS subset carries GitHub repo |
| `glama` | scrape | Glama MCP REST API (`glama.ai/api/mcp/v1/servers`) | **active (Phase B)** | 03:30 daily | feed-first; records carry `repository.url` |
| `mcp_so` | scrape | sitemap → `/server/<name>/<author>` item pages | **active (PR2)** | 03:45 daily | CF-proxied (curl_cffi); name from URL slug, repo from page |
| `claudeskills_info` | scrape | sitemap → `/skill/<slug>` item pages | **active (PR2)** | 04:00 daily | item-specific og tags; mostly `anthropics/skills` |
| `skillsmp` | scrape | sitemap → `/skills/<slug>` item pages | **active (PR2)** | 04:15 daily | CF-proxied (curl_cffi) |
| `skillhub_club` | scrape | sitemap → `/skills/<slug>` item pages | **active (PR2)** | 04:30 daily | Vercel; apex→www redirect |
| `skills_sh` | scrape | sitemap → `/<owner>/skills/<name>` item pages | **active (PR2)** | 04:45 daily | Vercel; owner segment = GitHub org |
| `pulsemcp` | scrape | sitemap → `/servers/<slug>` item pages | **active (PR2)** | 05:00 daily | CF-proxied; client-rendered listing → repo-sparse |
| `clawhub` | scrape | sitemap → item pages | **active (PR2, unreachable)** | 05:15 daily | host DNS currently dead → yields 0, logged, no crash |

> All 14 sources are now `enabled: true`. The 7 PR2 HTML scrapers share one
> configurable `SitemapHtmlAdapter` (`framework/sitemap_scraper.py`): each fetches a
> sitemap via curl_cffi (browser impersonation — most are Cloudflare-proxied and reject
> plain HTTPX), enumerates item-detail URLs, and reads the GitHub repo + name +
> description from each server-rendered item page. Per-site quirks (sitemap URL, item-URL
> filter, name source, repo denylist) live entirely in each `config/sources/<name>.yaml`
> `discovery` block — the adapter modules are one-line registrations.
>
> **Lean-stack contingencies (documented, acceptable):** `clawhub.dev` is DNS-unreachable
> today → its cycles are clean no-ops until the host returns. `pulsemcp.com` renders its
> listing client-side, so many items resolve no GitHub repo and stay in the fuzzy queue.
> A source that ever serves a genuine Cloudflare *challenge* (vs a normal CF-proxied 200)
> flips to `status='blocked'` — the Playwright-deferred contingency (no headless tier).
> Catalog-growth from these sources is best-effort, not a correctness gate.

## Take-down / halt procedure

If an aggregator asks us to stop, or a source must be paused for any reason:

1. The operator runs `uv run saferskills-admin sources pause <source> --reason
   "<reason>" --contact <email>` (the gated admin CLI over `POST /admin/sources/{source}/pause`).
2. `crawler_cursors.status` flips to `paused` within 60s; the cycle task no-ops on
   the next tick (it checks status before fetching).
3. Update the **Status** column in the table above.
4. `disabled` is permanent until manually re-enabled; `paused` is a temporary
   operator pause; `blocked` is a persistent technical block (e.g. a Cloudflare
   challenge under the lean stack).

See [`.claude/rules/ingestion.md` § Halt-source procedure](../.claude/rules/ingestion.md#halt-source-procedure)
for the contributor-facing detail and [`security.md` § Public-input handling](../.claude/rules/security.md)
for the outbound-allowlist contract (self-derived from each source YAML `hosts:` list).
