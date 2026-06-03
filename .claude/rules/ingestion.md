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
| `ScrapingAdapter` | Aggregator HTML/sitemap scraping (Phase B) |

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

## Procrastinate worker (D-04-03)

- **In-process worker** started in the **existing** `app/main.py` FastAPI lifespan, alongside the expiry sweep and startup hooks.
- Gated by `INGESTION_WORKER_ENABLED` (default `true`). Set `false` in test contexts that should not fan out external fetches.
- Advisory lock `0x5AFE5C13` (distinct from migration lock `0x5AFE5C11` and sweep lock `0x5AFE5C12`).
- Procrastinate schema applied via `procrastinate_app.schema_manager.apply_schema_async()` at startup — **never a migration**.
- Retry schedule: escalating 1 min → 5 min → 30 min → 6 h, then dead-letter (`IngestionRetry` exception). Per-adapter independent.
- Worker concurrency: `INGESTION_WORKER_CONCURRENCY` (default 4). INVARIANT: must be below `db pool_size + max_overflow` (10 + 20 = 30) so the API keeps headroom. See `crash-resilience-hardening` plan §1.
- The SCAN worker (`app/queue/scan_runner.py`) is **NOT Procrastinate** — it keeps its on-demand `asyncio.create_task` pattern per I-03 D-FE-34. Do not migrate it.

## HTTP client (D-04-06)

`HttpClientFactory.build(source_config)` returns an HTTPX async client with:

- **Hishel 1.x RFC-9111 cache** backed by `AsyncSqliteStorage` at `HISHEL_DB_PATH` (Fly volume mount). LRU cap `HISHEL_MAX_SIZE_BYTES` (default 500 MiB). TTLs: `HISHEL_GITHUB_TTL_SECONDS` (default 24h) for `api.github.com` / `raw.githubusercontent.com`; `HISHEL_AGGREGATOR_TTL_SECONDS` (default 1h) for scraped hosts. **304 revalidations are free vs the GitHub rate limit.**
- **SSRF allowlist transport** — same denylist as `security.md` § Public-input handling #2.
- **GitHub App token injection** — JWT (RS256, signed with `GITHUB_APP_PRIVATE_KEY`) exchanged for a 1h installation token; middleware auto-rotates before expiry.
- **Per-source rate limit** via `asyncio.Semaphore` + token bucket.
- **User-Agent**: `SaferSkillsBot/1.0 (+https://saferskills.ai/bot)`.
- **From**: `bot@saferskills.ai`.
- Timeouts: 30s connect, 60s read.

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

1. **robots.txt**: check via Protego (Phase B; cached 24h) before any fetch. If `Disallow`, skip + log.
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

## When to update this rule

| Change | Updates here |
|---|---|
| New adapter added | "Adding a provider" — confirm YAML + `pnpm run generate` (security.md/allowlist/loader are auto-derived); CHECK migration only for a brand-new value |
| Provider-registry generator change | "The YAML directory is the single source of truth" + `scripts/generate-ingestion-sources.cjs` + `schema-driven-development.md` pipeline table |
| Outbox payload shape change | "Outbox invariant" — re-verify no raw bytes in payload |
| Procrastinate version or retry schedule change | "Procrastinate worker" |
| HTTP client TTL / size cap change | "HTTP client" + `environment-config.md` + `app/core/config.py` |
| Conflict resolution rule change | "Conflict resolution" — needs a ratified deviation (see INDEX.md) |
| Classifier enum or heuristic change | "Agent-compatibility classifier" + `naming-conventions.md` if the agent enum changes |
| New ToS-respect mandate | "ToS-respect mandates" + adapter review checklist in PR template |
| Halt procedure change | "Halt procedure" + admin CLI docs |
| New source added to allowlist | "Outbound allowlist coupling" — add the YAML `hosts:` + `pnpm run generate` (self-derived; no `security.md`/validator hand edit) |
