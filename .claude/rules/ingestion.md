---
name: ingestion
description: Catalog ingestion rules — YAML-driven adapter framework, outbox invariant, ToS posture, conflict resolution, halt procedure
paths:
  - services/api/app/ingestion/**
  - schemas/ingestion-*.schema.json
  - schemas/merge-candidate.schema.json
  - tools/saferskills-admin/**
  - docs/sources.md
---

# Ingestion

> **Paths**: `services/api/app/ingestion/**`, `schemas/ingestion-*.schema.json`, `schemas/merge-candidate.schema.json`, `tools/saferskills-admin/**`, `docs/sources.md`

I-04 Phase A adds a Postgres-backed ingestion pipeline. This rule loads only when ingestion files are edited — see `documentation-sync.md` § Rule files at W1 for the full rule inventory.

## YAML-driven adapter framework

Every provider is declared in `app/ingestion/config/sources/<name>.yaml`, validated at startup into a `SourceConfig` (fields: `name`, `kind` ∈ `api|scrape|webhook`, `hosts` list, `cadence_cron`, `rate_limit_per_second`, `queue`, `enabled`, `discovery`, `policy`).

Adapters subclass one of three base classes:

| Base class | Use for |
|---|---|
| `RegistryAdapter` | Official-API sources (GitHub, npm, PyPI, MCP Registry) |
| `WebhookAdapter` | GitHub-push webhook dispatch |
| `ScrapingAdapter` | Aggregator feed/sitemap/HTML scraping (Phase B — implemented; see § Scrape fetch policy) |

Every adapter:
- Registers via `@register_adapter("<name>")` decorator.
- Implements `list_items()` + `normalize()` (and optionally `enrich()`).
- Reads its allowlisted hosts from the YAML `hosts:` list via `base_adapter.py`'s `source_hosts` property — adapters do **not** hardcode their own `name` or a `SOURCE_HOSTS` frozenset. The CI `validate` lane (`scripts/validate-outbound-allowlist.cjs`) derives the allowlist from the union of every YAML `hosts:` list and asserts every host an adapter actually fetches is declared there.

**Adding a provider = one YAML config file (+ one small adapter module, if needed).** `app/ingestion/tasks.py` loops the enabled YAML configs and registers periodic Procrastinate tasks automatically — no manual task registration.

## The YAML directory is the single source of truth (generator-derived)

`scripts/generate-ingestion-sources.cjs` (codegen STEP 0) reads every `config/sources/*.yaml` and emits the closed sets so a provider's identity lives in exactly one place:

- **`app/ingestion/config/generated/source_registry.py`** — `SOURCE_NAMES`, `REGISTRY_IDS`, `SOURCE_HOSTS` (per-source), `ALL_HOSTS` (the SSRF allowlist union). `loader.py` re-exports `SOURCE_NAMES` from here; `validate-outbound-allowlist.cjs` derives its allowlist from the same YAMLs.
- **The two hand-authored schema enum arrays** are rewritten in place (surgical, formatting-preserving): `schemas/ingestion-event.schema.json` → `source.enum` = sorted `SOURCE_NAMES`; `schemas/catalog-item.schema.json` → `…registryId.enum` = sorted(`REGISTRY_IDS` ∪ the fixed non-adapter set `user_submission`/`vendor_verified`/`upload`). These then flow into generated Pydantic/Zod/TS via the normal pipeline. **Never hand-edit those enum arrays** — edit the YAMLs and run `pnpm run generate` (the CI `validate` drift gate enforces this).

The `SourceConfig` carries `registry_id` (defaults to `name`); it equals `name` for every current source.

## Adding a provider

1. **Add the YAML** under `config/sources/<name>.yaml` (`name`, `kind`, `hosts`, `registry_id` (defaults to `name`), `cadence_cron`, `enabled`, `policy`, …). A disabled placeholder is `enabled: false`.
2. **`pnpm run generate`** — flows the new `name`/`registry_id`/`hosts` into `source_registry.py`, both schema enums, the generated Pydantic/Zod/TS, and the self-derived outbound allowlist. No hand edit to `security.md`, the validator, or the loader.
3. **Optional adapter module** under `sources/<name>.py` (`@register_adapter("<name>")`) if the provider needs custom fetch/normalize logic.
4. **DB CHECK migration (only for a brand-new value, NOT for the 14 already-shipped placeholders).** The value-list CHECKs are kept (DB-level closed-enum safety). A new built source needs one small mechanical migration that **hardcodes** the new value (migrations are frozen-in-time — never `import` the live generated set):

   ```python
   # migrations/versions/00NN_add_<name>_source.py
   def upgrade() -> None:
       # ingestion_events.source + crawler_cursors.source (cf. 0011)
       op.drop_constraint("chk_ingestion_events_source", "ingestion_events", type_="check")
       op.create_check_constraint("chk_ingestion_events_source", "ingestion_events",
           "source IN ('github_skills', …, '<name>')")
       op.drop_constraint("chk_crawler_cursors_source", "crawler_cursors", type_="check")
       op.create_check_constraint("chk_crawler_cursors_source", "crawler_cursors",
           "source IN ('github_skills', …, '<name>')")
       # item_sources.registry_id (cf. 0010) — only if registry_id != an existing value
       op.drop_constraint("chk_item_sources_registry_id", "item_sources", type_="check")
       op.create_check_constraint("chk_item_sources_registry_id", "item_sources",
           "registry_id IN ('github_skills', …, '<registry_id>')")
       # the framework expects a cursor row per source
       op.execute("INSERT INTO crawler_cursors (source) VALUES ('<name>')")

   def downgrade() -> None:
       # reverse: recreate the CHECKs without '<name>', delete the cursor row
       ...
   ```

## Outbox invariant (D-04-08)

**Every adapter fetch writes exactly one `ingestion_events` row in the SAME transaction as the catalog upsert.** This is the non-negotiable invariant: no write to `catalog_items` without a matching `ingestion_events` row, and vice versa.

- `ingestion_events.payload` is a normalized item snapshot (≤64 KiB, bounded per the schema). **It NEVER contains raw metadata-file bytes** — only per-file hashes. This is orthogonal to `artifact_blobs` (which stores bytes deliberately); the outbox payload stores hashes + conflicts + signals only.
- 304 responses produce an outbox row with `http_status=304`, `from_cache=true`, `body_sha256` = the cached body's hash.
- Setting `applied_at = now()` at commit marks the event as applied. `applied_at IS NULL` rows are retry candidates.
- Re-deriving the catalog from `ingestion_events` alone must produce the same state (replayable invariant). Vendor appeals reference `body_sha256` to prove the source content at fetch time.
- **`run_cycle` commits in batches** (`registry_adapter._COMMIT_BATCH`, 25 items) rather than once at the end — a full-feed crawl (mcp_registry ~10k items, each doing per-item enrich fetches) is durable + visible incrementally, and a mid-crawl failure keeps the committed prefix. The invariant holds **per item within a batch** (each catalog row + its `ingestion_events` row commit together); batching never splits a pair across commits.

## Procrastinate worker (D-04-03)

- **In-process worker** started in the **existing** `app/main.py` FastAPI lifespan, alongside the expiry sweep and startup hooks.
- Gated by `INGESTION_WORKER_ENABLED` (default `true`). Set `false` in test contexts that should not fan out external fetches.
- Advisory lock `0x5AFE5C13` (distinct from migration lock `0x5AFE5C11` and sweep lock `0x5AFE5C12`).
- Procrastinate schema applied via `procrastinate_app.schema_manager.apply_schema_async()` at startup — **never a migration**.
- Retry schedule: escalating 1 min → 5 min → 30 min → 6 h, then dead-letter (`IngestionRetry` strategy). Per-adapter independent. **Applies only to UNEXPECTED errors** (real bugs) that reach the generic `except Exception` in `run_source_cycle` (which keeps `logger.exception` + `raise`). **Expected provider/transport/operational failures** (`httpx.HTTPError`, `OSError`, non-blocked `IngestionError` — rate limit, 5xx, timeout, DNS, robots-disallow, oversize) are handled like the Cloudflare `AdapterBlockedError` branch: ONE clean `logger.warning("ingestion.cycle_failed", reason=…)` (**no stack trace**), a recorded `failed` run + bucketed `emit_ingestion_cycle_failed`, then **return without re-raising** — so neither our logger nor Procrastinate dumps a traceback and no pointless fast-retry storm fires (the periodic cron is the retry cadence). The shared `framework/failure.py::classify_failure` maps the exception to the `reason_enum` (it replaced the private `_classify_cycle_failure` and is reused by the scan path).
- **Retry taxonomy — permanent errors dead-letter immediately (WS-3).** `IngestionRetry.get_retry_decision` inspects the exception: a deterministic shape-drift / programming error (`KeyError`/`ValueError`/`TypeError`/`AttributeError`/`IndexError`/`pydantic.ValidationError`, via `retry.is_permanent_failure`) returns `None` (dead-letter NOW) — retrying just re-fails 4× with a full-feed refetch + traceback each. The 1m/5m/30m/6h escalation applies only to transient/unknown classes (`httpx.HTTPError`, `OSError`). `classify_failure` reports a permanent class as `reason_enum=permanent`.
- **Per-item isolation in `run_cycle` (WS-5).** A single poisoned item in a 10k-item crawl (a `ValueError`/`KeyError`/`TypeError`/`AttributeError` from provider shape-drift in normalize/enrich/upsert) becomes ONE clean `ingestion.item_skipped` WARN + a skipped outbox row + `continue` — never a whole-cycle traceback + retry storm. The cycle completes; `counters["items_skipped"]` records the count. (A collect-phase skip is pre-DB; a write-phase skip rolls back just that item's SAVEPOINT.)
- **Two-phase batching — no DB connection pinned across GitHub I/O (WS-6).** Each `_COMMIT_BATCH` is first PREPARED entirely outside any transaction (`normalize()` + `enrich()`'s multi-fetch network step hold NO pooled connection), then WRITTEN (upsert + outbox per item) in one short transaction and committed. Previously a connection was pinned through every item's enrich I/O for a whole batch, starving the shared API pool. The per-item outbox invariant (catalog row + its `ingestion_events` row in one commit) still holds per batch (D-04-08).
- Worker concurrency: `INGESTION_WORKER_CONCURRENCY` (default 4). INVARIANT: must be below `db_pool_size + db_max_overflow` (5 + 10 = 15) so the API keeps headroom — ingestion tasks draw their sessions from the **same** SQLAlchemy pool the public API serves from. **Asserted at startup** (`app/ingestion/worker.py::assert_worker_concurrency_budget`; the API refuses to boot on a bad budget). The shared pool's `DB_POOL_TIMEOUT_S` is the back-pressure lever (saturation → bounded 503, not a hang). See `crash-resilience-hardening` plan §1 + `environment-config.md`.
- **Worker concurrency = `INGESTION_WORKER_CONCURRENCY + SCAN_MAX_CONCURRENCY`** (the single worker drains the ingest queues + the `scan` queue; `worker.py::worker_concurrency`). Scan jobs are separately capped at `SCAN_MAX_CONCURRENCY` by an in-body semaphore.
- The **interactive** SCAN path (`app/queue/scan_runner.py::scan_run_repo`, called from `POST /scans`) is **NOT Procrastinate** — it keeps its on-demand `asyncio.create_task` pattern per I-03 D-FE-34. Only the **bulk** auto-scan (`tasks_scan.py`) is a Procrastinate job (scoped ratified deviation — see § Durable auto-scan pipeline + `tech-stack.md`). Do not migrate the interactive path.

## HTTP client (D-04-06)

`HttpClientFactory.build(source_config)` returns an HTTPX async client with:

- **Hishel 1.x RFC-9111 cache** backed by `AsyncSqliteStorage` at `HISHEL_DB_PATH` (Fly volume mount). LRU cap `HISHEL_MAX_SIZE_BYTES` (default 500 MiB). TTLs: `HISHEL_GITHUB_TTL_SECONDS` (default 24h) for `api.github.com` / `raw.githubusercontent.com`; `HISHEL_AGGREGATOR_TTL_SECONDS` (default 1h) for scraped hosts. **304 revalidations are free vs the GitHub rate limit.**
- **SSRF allowlist transport** — same denylist as `security.md` § Public-input handling #2.
- **GitHub App token injection** — JWT (RS256, signed with `GITHUB_APP_PRIVATE_KEY`) exchanged for a 1h installation token; middleware auto-rotates before expiry.
- **Per-source rate limit** via `asyncio.Semaphore` + token bucket.
- **User-Agent**: `SaferSkillsBot/1.0 (+https://saferskills.ai/bot)`.
- **From**: `bot@saferskills.ai`.
- Timeouts: 30s connect, 60s read.

## Scrape fetch policy (Phase B, lean — no headless browser)

`ScrapingAdapter` (`framework/scraping_adapter.py`) inherits the generic
`RegistryAdapter.run_cycle`; scrape adapters override only `list_items` / `normalize`
/ `enrich` — **never re-implement `run_cycle`**. It adds the scrape fetch primitives:

- **Discovery precedence (D-04-36): feed → sitemap → HTML.** `_fetch_feed` (JSON) and
  `_fetch_sitemap_urls` (XML `<loc>`, parsed XXE-safe via **`defusedxml`**) go through
  the **inherited HTTPX client** (SSRF allowlist transport + Hishel RFC-9111 cache).
  `_fetch_html` is the tier-1 fallback via **curl_cffi** (`AsyncSession(impersonate=
  "chrome131")`). `RawItem.payload_hint` records `discovery_path` ∈ {feed,sitemap,html}
  (+ optional `source_rank`); both flow to the outbox payload.
- **SSRF for non-HTTPX clients (hard rule).** curl_cffi bypasses the HTTPX
  `_SSRFTransport`, so `_fetch_html` calls `framework/allowlist.assert_host_allowed(url,
  self.source_hosts)` **before every request** — the single source of truth extracted
  from `_SSRFTransport` (`http_client.py` now delegates to it). **Any new non-HTTPX
  outbound client MUST call `assert_host_allowed` itself; the transport guard does not
  cover it.** Plus per-source `scraping_rate_limit.acquire_scrape_slot` (curl_cffi
  bypasses the HTTPX rate-limit hook too) + `robots.is_allowed`.
- **No Playwright tier.** A Cloudflare interstitial (`is_cloudflare_challenge`:
  `cf-mitigated` header, or a 403/503 from Cloudflare with a challenge body marker, or
  the `challenge-platform`+`cf-chl` script signature) raises `AdapterBlockedError`. The
  cycle wrapper (`tasks.run_source_cycle`) catches it, flips the source to
  `status='blocked'` (`_mark_source_blocked`), records the failed run, emits
  `ingestion_cycle_failed` `reason=cf_challenge`, and **returns without re-raising** (no
  retry storm — `is_source_paused` then no-ops future ticks). A blocked Cloudflare
  source is documented in `docs/sources.md`, not force-cracked.
- **Shared GitHub enrich.** Scrape adapters call `framework/github_enrich.enrich_repo_facts`
  (+ `parse_github_coords`) from `enrich()` — the `api.github.com` repo-facts +
  `raw.githubusercontent.com` manifest fetch factored out of `mcp_registry.enrich`. A
  feed without GitHub coordinates is a no-op (the item stays low-tier in the D-04-09
  fuzzy queue). **Each scrape YAML must declare `api.github.com` +
  `raw.githubusercontent.com` in `hosts:`** so the SSRF allowlist + GitHub-App-token
  hook cover the enrich fetch.
- **`kind: scrape` schedules automatically.** `tasks.py` registers a periodic task for
  every `enabled` source whose `kind ∈ {api, scrape}` has a `cadence_cron` (webhook
  sources are dispatched, not cronned). No per-adapter task wiring.
- **Feed adapters (PR1):** `smithery` (feed `registry.smithery.ai/servers`,
  `page`/`pageSize`) + `glama` (feed `glama.ai/api/mcp/v1/servers`, Relay `first`/`after`
  cursor). Glama records carry `repository.url` → real tiers; Smithery exposes GitHub
  only via the OSS subset's `homepage`.
- **HTML scrapers (PR2) — one shared `SitemapHtmlAdapter`** (`framework/sitemap_scraper.py`).
  The 7 sites (`mcp_so`, `pulsemcp`, `clawhub`, `skillsmp`, `skills_sh`, `claudeskills_info`,
  `skillhub_club`) share one shape: a sitemap (often a sitemap-**index**) enumerates
  item-detail URLs; each item page is server-rendered with `og:` meta + a GitHub link.
  The base fetches the sitemap via **curl_cffi** (most hosts are Cloudflare-proxied and
  reject plain HTTPX), recurses one level into child sitemaps matching `item_sitemap_substr`,
  filters item URLs by `item_url_regex`, caps at `max_items`, then per item extracts: the
  GitHub repo (first `github.com/<org>/<repo>` not in the global + per-site
  `github_denylist`), the name (`og:title` stripped of `name_strip`, branding split off;
  or the URL slug at `name_slug_index` when `name_from: slug`), and the description
  (`og:description`). **Every per-site difference lives in the YAML `discovery` block**, so
  each adapter module is a one-line `@register_adapter` subclass. Repo-less items still
  index (fuzzy queue); an unreachable host (clawhub's dead DNS) yields zero items + a log,
  never a crash; a genuine CF challenge raises `AdapterBlockedError` → `status='blocked'`.

> **Deps (Phase B):** `curl_cffi` (browser-impersonating tier-1 fetch), `trafilatura`
> (`extract_main_content`), `beautifulsoup4` + `lxml` (PR2 DOM parsing), `defusedxml`
> (XXE-safe sitemap parse). **No Playwright / Chromium.** lxml is pinned `>=6.0.1` (the
> first release with cp314 wheels; the plan's `~=5.3` predates Python 3.14).

> **No seed migration needed for the 9 Phase-B sources.** Migration `0011` already
> seeded one `crawler_cursors` row per source for all 14 (including the aggregators) and
> its CHECK constraints already include every aggregator value — so enabling a Phase-B
> adapter is YAML + adapter only, no DB migration (the "add a brand-new value" migration
> in § Adding a provider applies only to a source name not already in the enum).

## Schema-drift recovery (Windows codegen)

`pnpm run generate` now emits **LF on every platform** — the three Python-backed
generators force it at the source: `generate_sqlalchemy_models.py` writes with
`newline="\n"`, `generate_pydantic_models.py` LF-normalizes each
`datamodel-code-generator` output file (the external tool writes CRLF on Windows),
and `generate-openapi.cjs` strips CRLF from the captured Python stdout. So a local
Windows regen is byte-identical to CI and no longer produces phantom whole-file
diffs. (Root cause: Python's text-mode write translates `\n`→`\r\n` on Windows; the
Node-only generators were always LF. `.gitattributes` `* text=auto eol=lf` is the
belt — generators forcing LF is the braces.) If a stray CRLF ever reappears,
`git diff --ignore-all-space` still distinguishes EOL noise from real drift. A scrape
YAML change flows into `source_registry.py::ALL_HOSTS` (the self-derived outbound
allowlist) — that **is** a real diff and must be committed. **Inline `# comment` on a
YAML `hosts:` list entry breaks `validate-outbound-allowlist.cjs`** (its naive line
parser captures the comment into the host string) — put host-list comments on their
own lines.

## Enrichment + quality tiering (D-04-19)

`run_cycle` calls `adapter.enrich(client, normalized)` between `normalize()` and the merge — the hook that populates `metadata_files` (manifest/README) + repo signals (stars, a `size`-based commit-count proxy, default branch, license) the quality classifier needs. **An adapter whose listing feed carries no repo signals MUST implement `enrich()`**, or every item classifies `quality_tier='empty'` (`classify_quality_tier`: no README + no manifest + commit_count 0 → `empty`) and the default catalog gate (`quality_tier IN ('high','medium')`, the `list_items` soft gate) hides the whole source while the facet/header counts still count it.

- `github_topics` enriches from `raw.githubusercontent.com`; `mcp_registry` enriches from **both** `api.github.com` (repo facts) **and** `raw.githubusercontent.com` (mcp.json/server.json/README) — its YAML `hosts:` declares all three so the per-adapter SSRF allowlist + the GitHub-App-token hook (`http_client.py`, keyed on `api.github.com` in the host set) cover the fetch. Adding the hosts to the YAML + `pnpm run generate` is the only wiring needed (self-derived allowlist).
- **Re-tier on update**: `merger._apply_update` recomputes `quality_tier` from a re-crawled item **only** when it carries enrichment signals (`_has_enrichment_signals`: any `metadata_files`, `stars is not None`, or a `commit_count` proxy). This heals rows ingested before the source learned to enrich — but a cursor-based feed (mcp_registry) only re-yields a server on a **cursor reset**, so backfilling already-ingested rows requires resetting `crawler_cursors.updated_since` (e.g. to epoch) to force a full re-crawl. A signal-less aggregator update never downgrades a tiered row.

## Conflict resolution (D-04-11)

**GitHub always wins.** When sources disagree on author / description / license / etc., GitHub repo data (`SKILL.md`, `mcp.json`, `package.json`, `pyproject.toml`) is the source of truth. Other sources fill blanks but never override an existing GitHub-sourced value. Every disagreement is logged in `ingestion_events.payload.conflicts` with both values, the chosen value, and the reason.

## Dedup and fuzzy queue (D-04-09)

- The adapter **fetches** at repo granularity; the scan engine fans out per capability; the **upsert/auto-merge key is the capability slug** (see `naming-conventions.md` § Catalog slugs).
- Name-similarity matching runs ONLY for capabilities WITHOUT a resolved GitHub identity.
- Threshold for `merge_candidates` queue admission: RapidFuzz `token_set_ratio ≥ 85` OR Jaro-Winkler ≥ 0.90.
- Below threshold → ignored. Above threshold → `merge_candidates` row (`status=pending`). Founder resolves via `saferskills-admin merge-candidates list / approve / reject`.

## Agent-compatibility classifier (D-04-31)

Deterministic (no LLM) heuristic writes the **existing** `catalog_items.agent_compatibility` JSONB column. The stored enum values are the hyphenated 8-agent set:

```
claude-code | cursor | codex | copilot | windsurf | cline | gemini | openclaw
```

Rules (in priority order):
1. `anthropics/skills/*` OR `SKILL.md` at root → `claude-code`.
2. `mcp.json` `transport: stdio` → all 8 agents (universal MCP).
3. `mcp.json` `transport: streamable-http` or `sse` → `claude-code` + subset.
4. `.cursorrules` → `cursor`; `.windsurfrules` → `windsurf`; `.claude/hooks/` → `claude-code`.
5. Package name matches `mcp-server-*`, transport unspecified → all 8.
6. No signals → `claude-code` default (skill kind) or all 8 (mcp_server kind).

Classifier version stored on item for re-runnability: `uv run saferskills-admin catalog re-classify <slug>`.

## Content hash (D-04-16)

Content hash = JCS/RFC-8785 canonical SHA-256 of the artifact manifest + top-level file list + bytes. Stored on `catalog_items.content_hash_sha256`. Recomputed on every adapter cycle; hash change in a top-500 item triggers immediate Deep re-scan + Slack alert.

## ToS-respect mandates

All adapters MUST follow these rules regardless of source kind:

1. **robots.txt**: check via Protego (`framework/robots.is_allowed`; cached 24h) before any scrape fetch. If `Disallow`, the fetch raises `RobotsTxtDisallow` and the item is skipped + logged. Enforced by `ScrapingAdapter._fetch_html` (see § Scrape fetch policy).
2. **User-Agent + From**: declare on every request (see HTTP client above). Non-negotiable.
3. **Description length**: ≤ 280 characters, paraphrased. Never reproduce a full README or manifest body in the outbox payload or catalog row.
4. **Credit + backlink**: every catalog item sourced from an aggregator carries a `sources[].registryUrl` pointing back to the source listing.
5. **Rate limit**: default 1 req / 10s per source. Configurable in YAML `rate_limit_per_second`. Never exceed the declared limit, even if the remote allows it.

## Outbound allowlist coupling

The outbound allowlist is **self-derived from the YAML `hosts:` lists** — there is no hand-maintained host set in `security.md` or in `validate-outbound-allowlist.cjs`. A new source declares its hosts in its YAML; `pnpm run generate` flows them into `source_registry.ALL_HOSTS`, and the validator builds the allowlist from the same YAMLs. The `validate` CI lane's real guard is the **Python-fetch check**: it greps adapter `.py` files for outbound hosts and fails if any host is fetched but declared in no YAML `hosts:` list. **Never fetch a host in an adapter that isn't in its provider's YAML `hosts:` list.**

## Halt-source procedure

When an aggregator contacts us to request a stop, or when a source becomes unavailable:

1. Founder runs the Phase C admin CLI: `uv run saferskills-admin sources pause <source> --reason "<reason>" --contact <email>`.
2. The `crawler_cursors.status` column for that adapter flips to `paused` / `blocked` / `disabled` within 60s.
3. The cycle task no-ops on next tick (checks status before fetching).
4. `docs/sources.md` is updated to reflect the change.
5. `/sources` page reflects the new status.

The `disabled` state is permanent until manually re-enabled. `paused` is temporary (operator pause). `blocked` indicates a persistent technical block (e.g. Cloudflare tier-3 failure + no response from operator).

## Phase C periodic tasks (popularity / auto-scan / archive / authors / retention / alerts)

All run in the in-process Procrastinate worker under advisory lock `0x5AFE5C13`, registered via `import_paths` in `app/ingestion/__init__.py`. Each delegates to a testable session-taking inner function (`recompute_all`, `run_reconcile`, `run_archive_check`, `sweep_access_log`, `evaluate_alerts`) so the task wrapper is just `AsyncSessionLocal()` + the call. **Every catalog/scan query hard-filters `source_kind='github' AND visibility='public'`** — uploads + unlisted shadow rows are never ranked, auto-scanned, or archived (G-uploads invariant).

- **Popularity (`popularity_recompute`, nightly 02:00 + on-add `recompute_one_item`)** — the weighted-blend formula (D-04-13) lives in `app/ingestion/popularity.py`; weights are version-locked in the `popularity_formulas` table (`active=true` row, seeded `popularity_v1`). Writes `popularity_score` (the [0,1] score scaled to the 0-100 int column), `popularity_breakdown` (per-term jsonb), and `popularity_rank_tier` (`top500`/`top5k`/`long_tail`, rank-based — **distinct** from the pre-existing `popularity_tier` scan-tier). On-add is best-effort (a defer failure never breaks the merge — the nightly run is the guarantee).
- **Auto-scan — see § Durable auto-scan pipeline below.** (Replaces the popularity-gated `auto_scan_trigger_deep`/`_lite` triggers, which on a fresh DB never ran.)
- **Archive (`archive_check`, daily 03:00)** — flips `availability` on the 404 timeline (D-04-17): 3-6 consecutive 404s → `unavailable`; 7+ → `archived` (+`archived=true`); back to 0 → recover to `available`. The `consecutive404_count` is advanced inside the MergeEngine (a repo-level 404 fans across every capability row sharing the `github_url`); this task only reads it. Emits `catalog_item_archived` per archived row.
- **Authors (`author_summary_refresh`, nightly 04:30)** — `REFRESH MATERIALIZED VIEW CONCURRENTLY author_summary` (needs the autocommit connection, not a transaction).
- **Retention (`access_log_retention`, daily 04:00)** — DELETEs `access_log` rows older than 30 days (privacy.md § Retention). IPs are already /24-//48-redacted at write time, so this is a row sweep, not a redaction pass.
- **Alerts (`alert_evaluator`, every 15 min)** — per-source health from the `ingestion_events` outbox + `crawler_cursors.last_successful_cycle_at`, data-driven over the 14 YAML sources. **Warn** (failure_rate > 5% / 1h) → Sentry breadcrumb + PostHog `ingestion_cycle_failed`. **Page** (>25% / 1h OR >10% / 24h OR no successful cycle in 2× the YAML `cadence_cron`) → Slack `SLACK_ALERTS_WEBHOOK_URL`. A failure is any `http_status` not in {200, 304, 0}. The rug-pull/hash-change alert (D-04-16) was descoped from Phase C.

## Durable auto-scan pipeline

**Every indexed public-github capability is automatically + durably scanned.** Indexing leads to scanning — the catalog is never a wall of unscored rows. Lives in `app/ingestion/tasks_scan.py`; all three pieces run in the in-process Procrastinate worker. This is a **scoped ratified deviation to D-FE-34**: bulk scan is queue-shaped (durable Procrastinate jobs); the interactive `POST /scans` path stays `asyncio.create_task` (latency-sensitive, SSE). See `tech-stack.md`.

| Piece | What it does |
|---|---|
| `scan_capability_repo` (queue `scan`, `retry=3`, per-defer `queueing_lock`/`lock` = `scan:<github_url>`) | The durable per-repo scan **job**. Conditionally resolves the repo ref (`app/scan/fetch.py::resolve_ref` sends `If-None-Match`/`If-Modified-Since` from `repo_fetch_state` — a 304 is free), then: **unchanged ref + current rubric+engine** → skip (bump `last_checked_at`); **rubric/engine bump only (content same)** → re-evaluate from STORED `artifact_blobs` (no GitHub re-crawl, `source='rescan_rules'`); **content changed / never scanned** → full fetch + scan (`source='ingestion'`). **Size-gated hybrid fetch:** a repo whose reported `size` exceeds `SCAN_LARGE_REPO_SIZE_KB` (~20 MiB) skips the 25 MiB-capped tarball and uses `engine.run_repo_scan_via_trees` (Git Trees API — 1 REST call pinned to HEAD SHA — + per-blob `raw.githubusercontent.com` fetch of every file ≤5 MiB, bounded by `SCAN_TREES_MAX_FILES`/`_MAX_TOTAL_BYTES`/`_FETCH_CONCURRENCY`); a smaller repo uses `engine.run_repo_scan` (tarball). Because `size` is approximate, a tarball that blows the cap raises `TarballTooLargeError` (a `FetchError` subclass) and `_full_scan` retries once via the trees path before marking the run failed; a truncated tree / deleted repo / invalid ref stays a plain `FetchError` → run `failed` + recency stamped. Both paths converge on `_score_file_index` → `persist_completed_scan_run` with the identical fileset, so scores/snapshot/`.zip`/`content_hash_sha256` are byte-identical regardless of fetch path. Persists + stamps `last_scanned_at`/`scanned_*_version` on every public-github cap of the repo. Idempotent on `(github_url, ref_sha, rubric_version)`. Bounded by `SCAN_MAX_CONCURRENCY` (in-body semaphore). Pure decision helper: `decide_scan_action`. |
| `auto_scan_reconcile` (periodic, every 10 min, `queueing_lock`) | The coverage + versioned-re-eval + freshness **drainer**. Selects public-github `quality_tier IN ('high','medium')` not-archived repos that are `last_scanned_at IS NULL` (coverage) OR `scanned_rubric_version`/`scanned_engine_version` ≠ current (rule/engine bump) OR `last_checked_at < now() - SCAN_FRESHNESS_DAYS` (freshness), **popularity-first**, deduped per repo URL, bounded by `SCAN_RECONCILE_BATCH`, and `defer_scan_job`s each (the `queueing_lock` dedups against in-flight jobs). Testable inner: `run_reconcile`. Gated off by `SCAN_AUTOSCAN_ENABLED=false`. |
| `scan_stalled_retrier` (periodic, every 15 min) | Re-queues `scan`-queue jobs the worker abandoned on a restart (Procrastinate `get_stalled_jobs` + `retry_job`). |
| `ingestion_stalled_retrier` (periodic, every 15 min) | Sibling to `scan_stalled_retrier` for the **ingest** queues (`ingest_github`/`ingest_aggregator`/`ingest_mcp_registry`/`ingest_npm`/`ingest_pypi`/`periodic`) — `scan_stalled_retrier` is `queue="scan"` only, so without this a worker restart orphaned a `doing` ingest cycle forever (the ~1 orphaned cycle/hour leak, WS-7). Uses a generous `INGESTION_STALLED_SECONDS` (default 4h, comfortably above mcp_registry's worst-case cycle) so a long in-flight crawl is never re-queued out from under itself. |

- **Merger on-ingest hook** (`framework/merger.py::_defer_on_add_scan`) — best-effort `defer_scan_job` on a **new** item (after `_insert_new`) and on a **content-hash change** (the `content_hash_sha256 != raw_hash` branch in `_apply_update`), so a fresh arrival / drift scans promptly without waiting for the next drainer tick. The `queueing_lock` means the hook + the drainer can't double-enqueue. Fuzzy / no-coordinate rows never reach this branch. A defer failure never breaks the upsert (the drainer is the steady-state net).
- **Unified GitHub auth** — scan fetch (`app/scan/fetch.py`) shares the ingestion identity: `_auth_headers` prefers `GITHUB_TOKEN`, else the GitHub App installation token (`app/core/github_app_token.py`, the same provider the adapters use), else anonymous. One identity, one 5,000 req/h budget.
- **Feed exclusion** — `GET /api/v1/scans` excludes `source IN ('ingestion','rescan_rules')` (the bulk firehose); the feed is submissions + drift/appeal. Item scores still surface on `/items` + item pages.

## Admin endpoints + CLI (D-04-28)

`POST/GET /api/v1/admin/*` (`app/routers/admin.py`) are gated by the `X-Admin-Key` header (`SAFERSKILLS_ADMIN_KEY`; **fails closed** — every endpoint 403s when the secret is unset, **except** local development where `ENV=development` with no key configured is exempt and audits as the `local-dev` fingerprint; staging/production always set `ENV` so the exemption never applies on a deploy). Every mutation writes one `admin_audit_log` row (`security.md` § Audit Trail). Surface: `sources` (list / runs / pause / unpause / force-cycle), `merge-candidates` (list / decide), `catalog` (re-classify / inspect-events / archive / un-archive), `popularity` (recompute-now / top-n). `re-classify` re-runs the deterministic classifier on stored signals (no network re-fetch — `metadata_files` are reconstructed from the stored `kind_signals` so file-derived kind/agent classifications are preserved).

### Eagle-eye health view (ingestion observability)

`GET /admin/sources` is the **eagle-eye pipeline snapshot** — additive over the original list (every prior field name preserved): a top-level `generated_at` + `summary` (overall `healthy`/`degraded`/`critical` rollup, `by_status` counts, `critical_count`/`warn_count`) + deduped `critical[]` (one highest-severity signal per source), and per provider the nested `live` / `last_run` / `schedule` / `health` objects. Built from cheap reads only — `crawler_cursors` (status/streak/last-success), `ingestion_runs` (last run + rolling 1h/24h failure windows + oldest running row), and `procrastinate_jobs` (live `doing` → `live.running`, exhausted `failed` → `dead_letter`, pending `scheduled_at` → `schedule.next_retry_at`) — fed through the **pure** state machine in `app/ingestion/framework/health.py` (8 states `disabled/blocked/paused/running/never_run/failing/overdue/healthy`; critical reason-codes `blocked/dead_letter/stuck/stale/failure_rate/consecutive_failures`, warn `paused/overdue/failure_rate_warn`). It imports the failure-rate thresholds + `cadence_seconds` from `framework/alerts.py` so the dashboard and the 15-min pager agree. `procrastinate_jobs` is guarded by `to_regclass` (absent on a fresh DB / under the test transport).

`GET /admin/sources/{source}/runs` is the keyset-paginated (`limit` ≤200, `before` on `started_at`) `ingestion_runs` drill-down (`{"data":[…], "next_before":…}`, 404 on unknown source). Both are reads → no `admin_audit_log` write.

The operator CLI is the **separate** `tools/saferskills-admin/` uv package (a thin Typer client over these endpoints — no DB access; mirrors `tools/data-seed/` but mutates production). Dangerous verbs (`merge-candidates approve/reject`, `catalog archive/un-archive`, `sources disable`, `popularity recompute-now`) require `--yes` or `SAFERSKILLS_ADMIN_CONFIRM=yes-i-mean-it` (`shared/safety.py`). The `sources` group adds **`sources dashboard`** (a `textual` TUI over the eagle-eye snapshot — navigable 14-source overview → per-source drill-down → force-cycle/pause/unpause via a confirm modal, 5s auto-refresh) + **`sources runs <source>`** (scriptable history); `sources list`/`status` project a flat column subset from the enriched payload.

## When to update this rule

| Change | Updates here |
|---|---|
| New adapter added | "Adding a provider" — confirm YAML + `pnpm run generate` (security.md/allowlist/loader are auto-derived); CHECK migration only for a brand-new value |
| Scrape fetch policy / tier / Cloudflare handling change | "Scrape fetch policy" + `framework/scraping_adapter.py` + `tasks.run_source_cycle` blocked path + `docs/sources.md` |
| New non-HTTPX outbound client | "Scrape fetch policy" § SSRF — it MUST call `allowlist.assert_host_allowed` itself |
| Provider-registry generator change | "The YAML directory is the single source of truth" + `scripts/generate-ingestion-sources.cjs` + `schema-driven-development.md` pipeline table |
| Outbox payload shape change | "Outbox invariant" — re-verify no raw bytes in payload |
| Procrastinate version or retry schedule change | "Procrastinate worker" |
| HTTP client TTL / size cap change | "HTTP client" + `environment-config.md` + `app/core/config.py` |
| Conflict resolution rule change | "Conflict resolution" — needs a ratified deviation (see INDEX.md) |
| Classifier enum or heuristic change | "Agent-compatibility classifier" + `naming-conventions.md` if the agent enum changes |
| New ToS-respect mandate | "ToS-respect mandates" + adapter review checklist in PR template |
| Halt procedure change | "Halt procedure" + admin CLI docs |
| New source added to allowlist | "Outbound allowlist coupling" — add the YAML `hosts:` + `pnpm run generate` (self-derived; no `security.md`/validator hand edit) |
| Popularity formula / weights change | "Phase C periodic tasks" — bump `popularity_formulas` (new `active` row + migration) + `app/ingestion/popularity.py` |
| Auto-scan pipeline change (drainer / scan job / change-gate / merger hook) | "Durable auto-scan pipeline" — `app/ingestion/tasks_scan.py` + the `last_scanned_at`/`scanned_*_version` columns + `repo_fetch_state` (`database.md`) + the `SCAN_*` vars (`environment-config.md`) |
| Archive timeline / alert-tier threshold change | "Phase C periodic tasks" — `tasks_archive.py` / `framework/alerts.py` |
| New admin endpoint / CLI verb | "Admin endpoints + CLI" + `app/routers/admin.py` (+ `admin_audit_log`) + `tools/saferskills-admin/` + `security.md` Audit Trail; dangerous verbs → `shared/safety.py::DANGEROUS_OPS` |
| Eagle-eye health state / reason-code / snapshot-shape change | "Eagle-eye health view" + `app/ingestion/framework/health.py` + `database.md` § Ingestion runs; keep thresholds shared with `framework/alerts.py` |
