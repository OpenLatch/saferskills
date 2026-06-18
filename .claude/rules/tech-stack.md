# Tech Stack

The stack below is the contract. Every dep tracks its current latest major or latest stable minor; Dependabot drives weekly bumps grouped by update-type (cf. `ci-cd.md`).

## Stack table

| Layer | Tool | Version policy |
|---|---|---|
| **Runtime — backend** | Python 3.14 | Latest stable. Use `python` everywhere; never `python3` on Windows. |
| **Runtime — frontend** | Node 24 LTS | Latest LTS. |
| **Runtime — CLI** | Rust (stable, edition 2021, MSRV 1.88) | Single crate in `cli/` (the `saferskills` install CLI). Mirrors `openlatch-client`'s toolchain + architecture; `rust-toolchain.toml` pins `channel = "stable"`. Overrides the original "TypeScript-SEA" CLI decision (deliberate exception). |
| **Package manager — backend** | uv | Latest. |
| **Package manager — frontend** | pnpm 10 | Latest. |
| **Package manager — CLI** | cargo | Latest. **Scoped to `cli/` only** — the "never mix" mandate gains a Rust-in-`cli/` carve-out (see Mandates). |
| **API framework** | FastAPI 0.136+ | Latest minor. |
| **Validation** | Pydantic 2.13+ | v2 only. |
| **ORM** | SQLAlchemy 2 (async) | Async-only — `AsyncSession` everywhere. |
| **Migrations** | Alembic | Latest. |
| **Database** | PostgreSQL 17 | Latest GA. Single Postgres — no Redis, no other store. |
| **Frontend framework** | Astro 6 + React 19 islands | Deliberate divergence from openlatch-platform (which uses Vite + React 19 SPA). Islands via `client:idle`/`client:load`/`client:visible`. |
| **CSS** | Tailwind v4 | No `tailwind.config.js`; tokens live in `ui/styles/tokens.css` per `design-system.md`. |
| **UI primitives** | shadcn/ui (Radix + Tailwind) | Component code lives under `ui/components/`; never imported from a registry at build time. |
| **Lint + format** | Biome 2.4 | One tool for TS/JS/JSON — replaces both ESLint and Prettier. |
| **Lint + format — Python** | Ruff | Lint + format in one pass. |
| **Type-check — Python** | Pyright | Strict mode in CI. |
| **Type-check — Frontend** | `tsc --noEmit` + `astro check` | Both required in CI. |
| **Unit tests — Frontend** | Vitest 4 | ≥70% line coverage. |
| **Unit tests — Backend** | pytest | ≥70% line coverage. |
| **E2E** | Playwright 1.60 | Under `tools/e2e/`. |
| **Story browser** | Ladle | Replaces Storybook (lighter, Vite-native — runs alongside Astro for component browsing only). |
| **Codegen** | `pnpm run generate` — 9 generators in order | See `schema-driven-development.md`. |
| **CLI crate stack** | clap 4.6 (+`clap_complete`/`clap_mangen`); inquire; indicatif; the `search` TUI (ratatui 0.29 + crossterm 0.28 + nucleo 0.5 + futures-util — draws to **stderr**, stdout stays machine-clean); reqwest 0.12 **rustls-only**; tokio; toml/toml_edit + jsonc-parser; zip 8; **ed25519-dalek 2 (verify-only) + base64** (the `scan agent` pack-signature pre-flight); anyhow/thiserror/miette; serde/serde_json. `Cargo.toml` is the source of truth. | **rustls-only is CI-enforced** (`cli-rustls` greps the dep tree for `openssl-sys`/`native-tls`) — every crate above is TLS-free of OpenSSL. Release binary **~5.1 MB** (< the 15 MB `cli-build` gate); `[profile.release] opt-level="z", lto, codegen-units=1, strip, panic="abort"`. |
| **CLI distribution** | npm (prebuilt platform binaries via `optionalDependencies` + postinstall fallback) + crates.io | Unscoped `saferskills` main package (so `npx saferskills install` works); scoped `@openlatch/saferskills-<platform>` deps; `cargo install saferskills`. Both via OIDC Trusted Publishing (no tokens); cosign keyless signatures + Syft SBOM per artifact. Hand-rolled on the existing `release-please` (rust) + `publish-npm.yml` rails — **NOT cargo-dist**. |
| **Container** | Docker + Compose | Local-dev orchestrator; Fly.io for prod. |
| **CI** | GitHub Actions | All actions SHA-pinned; `harden-runner` first step. |
| **Observability** | Sentry (errors) + PostHog (product analytics) + OpenTelemetry (traces/metrics) | Sentry + OTel projects are SaferSkills-specific — separate from OpenLatch. **PostHog is the exception**: one shared OpenLatch-portfolio project for cost (2026-06-04), SaferSkills events tagged `product: "saferskills"`. See `telemetry.md`. |
| **Email** | Resend | Outbound only. Single verified sending domain `notifications.openlatch.ai` shared with OpenLatch (cost decision 2026-05-28); `From: SaferSkills <…@notifications.openlatch.ai>`, reply-to on `@openlatch.ai` mailboxes. Disclosed on `/about`. |
| **Task queue (ingestion only)** | Procrastinate 3.x | PG-backed (no Redis). In-process worker via FastAPI lifespan (advisory lock `0x5AFE5C13`). Schema applied at startup via `procrastinate_app.schema_manager.apply_schema_async()` — never a migration. SCAN worker keeps `asyncio.create_task`. New ingestion deps: `hishel ~= 1.2` (RFC-9111 cache), `rapidfuzz ~= 3.10` (fuzzy dedup), `croniter ~= 6.0` (cron parsing), `rfc8785` (JCS canonical hash), `protego` (robots.txt), `psycopg[binary]` (Procrastinate sync driver), `cryptography` (GitHub App JWT). |
| **Aggregator scrape stack (ingestion)** | curl_cffi + trafilatura + bs4/lxml + defusedxml | **Lean — NO Playwright/Chromium** (deliberate: keeps the Fly image small). `curl_cffi ~= 0.13` (browser-impersonating tier-1 HTML fetch, Cloudflare-aware), `trafilatura ~= 2.0` (main-content extraction), `beautifulsoup4 ~= 4.12` + `lxml >=6.0.1,<7` (DOM parsing; lxml 6.0.1+ is the first with cp314 wheels — `~=5.3` predated Python 3.14), `defusedxml ~= 0.7` (XXE/billion-laughs-safe sitemap parse). A Cloudflare-gated source lands `blocked`, not force-cracked. See `ingestion.md` § Scrape fetch policy. |

## Mandates

- **pnpm for TS/JS, uv for Python, cargo for the Rust CLI — never mix.** No `npm install`, no `pip install`, no `poetry`. **Cargo is scoped to `cli/` only** (the Rust install CLI); never introduce cargo elsewhere. The npm publish of the CLI is a *distribution* artifact (prebuilt binaries), not a Node build — `cli/npm/` ships no source.
- **All Astro/React component code is framework-agnostic React 19 + Tailwind primitives** — never import Astro APIs from `ui/components/`. The `ui/` package is portable; Astro lives only in `webapp/src/pages/`.
- **The codegen pipeline is the source of truth.** `pnpm run generate` is the only entry point (generator inventory + count: `schema-driven-development.md`).
- **Single Postgres** — in-process LRU caches mirror data inside the process; never reach for Redis.
- **Artifact storage is in-Postgres by design.** Stored scan-file snapshots (`artifact_blobs`, content-addressed dedup) live in the single Postgres as `bytea` — no object store / bucket / new secret. This **preserves** the single-store rule above; it does not amend it. See `database.md`.
- **Procrastinate runs ingestion + the durable bulk-scan queue.** It owns the ingest queues + a `scan` queue (the auto-scan pipeline: `scan_capability_repo` jobs + the `auto_scan_reconcile` drainer + a stalled-job retrier — `app/ingestion/tasks_scan.py`). **Deliberate exception for bulk scan**: *bulk* scan is queue-shaped (durable, retried, stalled-recovery, `queueing_lock` dedup, worker-concurrency-bounded), so it is a Procrastinate job; the *interactive* `POST /scans` path stays on-demand `asyncio.create_task` (latency-sensitive, SSE — do **not** migrate it). The single in-process worker drains both (concurrency = `INGESTION_WORKER_CONCURRENCY + SCAN_MAX_CONCURRENCY`, asserted < the pool). Do not add Procrastinate to other subsystems without a new deliberate exception.

## Forbidden tools

| Tool | Why it's forbidden |
|---|---|
| **ESLint** | Biome does both lint and format. |
| **Prettier** | Biome formats. |
| **npm / yarn** | pnpm only. |
| **pip / poetry / pipenv** | uv only. |
| **Redis / Memcached** | In-process LRU; no out-of-process cache. |
| **Bun / Deno** | Node 24 LTS only. |
| **Vite** | Astro 6 is the deliberate divergence — Vite ships under Astro's hood but is not directly invoked. |
| **Auth sidecar (Express + better-auth)** | No auth yet; when auth ships, an auth strategy is selected then. Don't introduce a sidecar speculatively. |
| **Storybook** | Ladle. |
| **Webpack / Rollup direct usage** | Astro handles bundling. |
| **cargo-dist** | The CLI release pipeline is hand-rolled on the existing `release-please` + `publish-npm.yml` rails (mirrors openlatch-client). No `dist-workspace.toml`. |
| **OpenSSL / native-tls in the CLI** | The Rust CLI is rustls-only; `openssl-sys` / `native-tls` in the dep tree fails the `cli-rustls` CI lane. |

## Version-bump policy

- **Dependabot** is the only dep-bot. Weekly Monday across every ecosystem (npm root + pip `services/api` + pip `tools/e2e` + docker + github-actions).
- Every dep on its current latest major or latest stable minor.
- Bumps are grouped per ecosystem to keep the PR queue small. Minor/patch bumps group under `frontend-minor-patch` / `api-minor-patch` / etc. Major bumps group under `frontend-major` / `api-major` — landed as a single PR per ecosystem per Monday with a combined migration note in the PR body. Source of truth: `.github/dependabot.yml`.

## When to update this rule

| Change | Updates here |
|---|---|
| New runtime / framework / dep added | "Stack table" |
| Tool deprecated / replaced | "Stack table" + "Forbidden tools" if previously allowed |
| New mandate or anti-pattern | "Mandates" / "Forbidden tools" |
| Version-bump source / policy change | "Version-bump policy" + `ci-cd.md` Dependency-bump policy |
