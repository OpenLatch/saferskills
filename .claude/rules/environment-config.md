---
paths:
  - "services/api/.env*"
  - "webapp/.env*"
  - "docker-compose*.yml"
  - "services/api/app/core/config.py"
  - "webapp/src/env.ts"
---

# Environment Config

> **Paths**: `services/api/.env*`, `webapp/.env*`, `docker-compose*.yml`, `services/api/app/core/config.py`, `webapp/src/env.ts`

## Purpose

All env vars are read through a typed wrapper — `pydantic-settings` on the backend, a Zod-validated `env.ts` module on the frontend. **Never read `os.environ` / `process.env` / `import.meta.env` directly in feature code.** This guarantees: typed access, default values in one place, fail-fast on missing required vars.

## W1 env vars

### Backend (`services/api/app/core/config.py`)

| Var | Required | Default | Purpose |
|---|---|---|---|
| `DATABASE_URL` | yes | (none) | PostgreSQL connection string. Auto-normalized by `config.py::_normalize_db_dsn`: a managed-Postgres `postgres://` / `postgresql://` DSN is coerced to `postgresql+asyncpg://`, and a libpq `?sslmode=…` query param (Fly Managed Postgres / Supabase / Neon) is renamed to asyncpg's `?ssl=…` — without it the asyncpg dialect crashes `alembic upgrade head` at boot (`connect() got an unexpected keyword argument 'sslmode'`) and the API drops into degraded mode. |
| `DB_POOL_SIZE` | no | `5` | SQLAlchemy persistent pool size (crash-resilience §1). The API + every ingestion task draw sessions from here. Lowered from 10 to keep idle-connection RAM modest on the `shared-cpu-1x:256MB` Postgres; scale up by config with prod RAM. |
| `DB_MAX_OVERFLOW` | no | `10` | SQLAlchemy burst overflow above `DB_POOL_SIZE` (released when idle) → 15 max SQLAlchemy slots / Machine. |
| `DB_POOL_TIMEOUT_S` | no | `10` | Seconds a checkout waits for a free SQLAlchemy connection before raising `TimeoutError` — the back-pressure lever. The API maps it to a bounded **503** (`app/main.py` exception handler) instead of hanging every request until the worker frees a slot. |
| `ASYNCPG_POOL_MAX_SIZE` | no | `5` | asyncpg LISTEN/NOTIFY pool max size (SSE + scan worker). Was hard-coded 10. |
| `INGESTION_QUEUE_POOL_MAX_SIZE` | no | `5` | Procrastinate job-queue connector pool max size (passed explicitly to `PsycopgConnector` → `psycopg_pool.AsyncConnectionPool`, never the library default). Task DB work uses the SQLAlchemy pool, not this one. |
| `SENTRY_DSN` | no | unset | Errors-only Sentry project (cf. `telemetry.md`) |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | no | unset | OpenTelemetry collector |
| `ENV` | yes | `development` | One of `development` / `staging` / `production` — drives Sentry env tag and log format. (Does NOT gate migrations: `alembic upgrade head` runs in-process on every boot in all envs — see `ci-cd.md` § Deployment.) |
| `LOG_LEVEL` | no | `INFO` | Python logging level |
| `CORS_ALLOWED_ORIGINS` | yes | `http://localhost:4321` | Comma-separated origin list. With the webapp's same-origin `/api/*` proxy the browser never calls cross-origin, so CORS is exercised only by direct/tooling callers. |
| `SAFERSKILLS_PROXY_SHARED_SECRET` | no | unset | Shared secret proving a request came from the trusted same-origin webapp proxy. When set, the per-IP rate limiter trusts the left-most `X-Forwarded-For` (the real visitor the proxy preserved) **only** on requests whose `X-Proxy-Secret` header matches (constant-time) — so a direct caller to the public API cannot spoof XFF to dodge the cap. **Must equal the webapp's `SAFERSKILLS_PROXY_SHARED_SECRET`** (frontend table). Unset (dev/test) → the raw TCP peer is used. The loopback exemption always keys on the real peer, never XFF. **Delivery:** a SECRET — staged via `flyctl secrets set --stage` in `deploy.yml` (per API env), not a committed `[env]`. See `security.md` § Public-input handling #11 + `scans.py::_rate_limit_ip` + `ci-cd.md` § Deployment. |
| `SCAN_SUBMIT_DAILY_LIMIT` | no | `10` | Max scan submissions per IP per 24h (D-FE-11), **shared by `POST /scans` and `POST /scans/upload`**. Loopback callers are exempt (trusted local seeding) — see `security.md` § Public-input handling #5. |
| `ARTIFACT_DOWNLOAD_DAILY_LIMIT` | no | `200` | Max stored-snapshot `.zip` downloads per IP per 24h (`GET /items/{slug}/download`). Same loopback exemption — see `security.md` § Public-input handling #6. |
| `PUBLIC_BASE_URL` | no | `http://localhost:4321` | Public webapp origin. Builds the unlisted `share_url` + the upload source `registryUrl`. |
| `PRIVATE_LOOKUP_DAILY_LIMIT` | no | `60` | Max unlisted-run lookups (`GET /scans/r/{token}`) per IP per 24h (bucket `private_lookup`). Same loopback exemption — see `security.md` § Public-input handling #7. |
| `UPLOAD_MAX_BYTES` | no | `10485760` | Hard cap (10 MiB) on a `POST /scans/upload` body — enforced while streaming. |
| `UPLOAD_EXTRACT_MAX_PER_FILE_BYTES` | no | `5242880` | Per-file cap (5 MiB) when extracting an uploaded `.zip`. |
| `UPLOAD_EXTRACT_MAX_TOTAL_BYTES` | no | `52428800` | Total uncompressed cap (50 MiB) for an uploaded `.zip`. |
| `UPLOAD_EXTRACT_MAX_RATIO` | no | `100` | Max compression ratio (zip-bomb guard). |
| `UPLOAD_EXTRACT_MAX_ENTRIES` | no | `1000` | Max entry count in an uploaded `.zip`. |
| `UPLOAD_ALLOWED_EXTENSIONS` | no | `.zip,.md,.json,.yaml,.yml,.toml,.txt,.js,.ts,.py,.sh` | Comma-separated upload extension allowlist. |
| `UNLISTED_RETENTION_DAYS` | no | `90` | TTL for unlisted runs — sets `scan_runs.expires_at`; swept by `app/core/sweeps.py`. |
| `UPLOAD_RESCAN_WINDOW_DAYS` | no | `90` | Window during which an upload may be re-scanned. |
| `SWEEP_INTERVAL_SECONDS` | no | `3600` | In-process expiry-sweep loop interval (advisory lock `0x5AFE5C12`). See `database.md` § Expiry sweep. |
| `VENDOR_SESSION_SECRET` | yes (prod) | dev-insecure default | HS256 signing key for the vendor right-of-reply session JWT (`ss_vendor_session` cookie). The API is the sole verifier — the webapp stores the JWT opaquely and forwards it as a Bearer token. 32+ random bytes in prod; rotate quarterly (rotation only invalidates in-flight 15-min sessions). I-03 Phase C. |
| `GITHUB_TOKEN` | no | unset | Optional GitHub PAT. Raises the 60→5,000 req/h limit for scan-tarball fetches + the hourly `/api/v1/stats` `github_stars` proxy. Unauthenticated is fine for the single cached hourly call. Emits no PII (cached count only, cf. `telemetry.md`). |
| `TURNSTILE_SECRET_KEY` | yes (staging/prod) | unset | Cloudflare Turnstile `siteverify` secret for the scan-submit human gate (`POST /scans` + `POST /scans/upload`). Unset → `verify_turnstile` bypasses (dev/test/CI). A `model_validator` in `config.py` **hard-fails boot** when this is unset and `ENV` is `staging`/`production`, so a deploy never runs the gate open. Verified server-side against `challenges.cloudflare.com` before any scan work; fail-closed on a Cloudflare outage. Loopback (trusted seed) exempt. See `security.md` § Public-input handling #10. Non-prod uses Cloudflare's always-pass test secret `1x0000000000000000000000000000000AA`. **Delivery:** sourced from the GH Actions secret `TURNSTILE_SECRET_KEY` and **injected into Fly by the deploy workflow** — `flyctl secrets set --stage` before `flyctl deploy`, per API env (`saferskills-api-staging` / `saferskills-api`). It is NOT a build-arg (runtime-only). See `ci-cd.md` § Deployment. |
| `INGESTION_WORKER_ENABLED` | no | `true` | Start the in-process Procrastinate ingestion worker (advisory lock `0x5AFE5C13`). Set `false` in test contexts that must not fan out external fetches. |
| `INGESTION_WORKER_CONCURRENCY` | no | `4` | Procrastinate worker concurrency. INVARIANT: `INGESTION_WORKER_CONCURRENCY + SCAN_MAX_CONCURRENCY` must stay below `DB_POOL_SIZE + DB_MAX_OVERFLOW` (5 + 10 = 15), leaving API headroom; **asserted at startup** (`app/ingestion/worker.py::assert_worker_concurrency_budget` — the API refuses to boot otherwise). The single in-process worker drains both the ingest queues and the `scan` queue (concurrency = the sum); scan jobs are separately capped by `SCAN_MAX_CONCURRENCY`. See `tech-stack.md` § Procrastinate mandate + crash-resilience addendum §1.5. |
| `SCAN_AUTOSCAN_ENABLED` | no | `true` | Enable the durable auto-scan pipeline (the reconciliation drainer `auto_scan_reconcile` + the merger on-ingest scan hook). `false` pauses all bulk scanning locally without touching the interactive `POST /scans` path. See `ingestion.md` § Durable auto-scan pipeline. |
| `SCAN_MAX_CONCURRENCY` | no | `4` | Max concurrent durable `scan_capability_repo` jobs (in-body semaphore). Part of the pool-budget invariant above. Keep single-digit (we're GitHub-rate-limited anyway; avoids the Procrastinate SKIP-LOCKED cliff). |
| `SCAN_RECONCILE_BATCH` | no | `200` | Max repos the reconciliation drainer enqueues per tick (popularity-ordered). Bounds a 10k-burst; the `queueing_lock` dedups against in-flight jobs. |
| `SCAN_FRESHNESS_DAYS` | no | `30` | Periodic cheap re-check cadence — a repo whose `last_checked_at` is older than this is re-resolved (a 304 / unchanged ref just bumps `last_checked_at`, no scan). |
| `GITHUB_APP_ID` | no | unset | GitHub App `saferskills-ingest` numeric App ID (founder outbox 01). Required in production for the ingestion worker. |
| `GITHUB_APP_PRIVATE_KEY` | no | unset | GitHub App PEM private key (RS256, multi-line). Store base64-encoded in a Fly secret. |
| `GITHUB_APP_INSTALLATION_ID` | no | unset | GitHub App installation ID (numeric). |
| `GITHUB_WEBHOOK_SECRET` | no | unset | HMAC-SHA256 secret for `X-Hub-Signature-256` verification on `POST /webhooks/github`. |
| `HISHEL_DB_PATH` | no | `/data/.hishel.db` | Hishel RFC-9111 SQLite cache path (Fly volume mount). |
| `HISHEL_MAX_SIZE_BYTES` | no | `524288000` | Hishel cache LRU size cap (500 MiB). |
| `HISHEL_GITHUB_TTL_SECONDS` | no | `86400` | Hishel cache TTL for `api.github.com` / `raw.githubusercontent.com` (24h). |
| `HISHEL_AGGREGATOR_TTL_SECONDS` | no | `3600` | Hishel cache TTL for scraped aggregator hosts (1h). |
| `INGESTION_SOURCE_BLOCKLIST` | no | `` (empty) | Comma-separated source names disabled in this env (e.g. `mcp_so`). |
| `INGESTION_GITHUB_CODE_SEARCH_ENABLED` | no | `false` | Enable the `github_topics` code-search discovery pass (D-04-35). Default off in Phase A1. |
| `SLACK_ALERTS_WEBHOOK_URL` | no | unset | Slack incoming-webhook URL for `#saferskills-alerts` (Phase C ingestion failure alerts; outbox 03). |
| `SAFERSKILLS_ADMIN_KEY` | no | unset | Shared secret gating `GET/POST /api/v1/admin/*` via the `X-Admin-Key` header (Phase C, D-04-28). Generated by `saferskills-admin auth gen-admin-key`. Unset + `ENV=development` → keyless local access (no `X-Admin-Key` needed; audits as `local-dev`) so the operator CLI works on a dev machine; unset + staging/production → every admin endpoint returns 403 (fails closed). **Delivery:** a SECRET — staged via `flyctl secrets set --stage` in `deploy.yml` (API apps) from an **environment-scoped** GH Actions secret (distinct value per env), never a committed `[env]`. Replaced by SSO when auth lands (Track E). |

> **Artifact storage needs no new env/secret.** Stored scan snapshots
> (`artifact_blobs`, content-addressed) live in the single Postgres (`DATABASE_URL`)
> — no object store, no bucket creds, no extra var. Preserves the single-store
> rule (`tech-stack.md`). See `database.md`.

### Frontend (`webapp/.env.example`)

Frontend env vars MUST be prefixed `PUBLIC_*` (Astro convention) to be exposed at build time. Anything not prefixed stays server-side only.

| Var | Required | Default | Purpose |
|---|---|---|---|
| `API_ORIGIN` | no | `http://localhost:8000` | **Server-only, RUNTIME** (intentionally NOT `PUBLIC_*`, so it is per-environment without a rebuild — set in `webapp/fly.*.toml` + `docker-compose.yml`). The backend origin the in-app `/api/*` reverse proxy (`webapp/src/pages/api/[...path].ts`) forwards to, and the base for SSR/prerender-build fetches (`env.ts` server branch). The browser never sees it. |
| `SAFERSKILLS_PROXY_SHARED_SECRET` | no | unset | **Server-only, RUNTIME secret** (NOT `PUBLIC_*`). The `/api/*` proxy sends it as the `X-Proxy-Secret` header so the API trusts the forwarded visitor IP for per-IP rate limiting. **Must equal the API's `SAFERSKILLS_PROXY_SHARED_SECRET`** (backend table). Unset → no header (the API keys rate limits on the raw peer). **Delivery:** a Fly **runtime secret** on the webapp app — staged via `flyctl secrets set --stage` in `deploy.yml` (the proxy reads it at request time, so it is not a build-arg). See `security.md` § Public-input handling #11. |
| `PUBLIC_API_URL` | no | `http://localhost:8000` | **Local-dev/test fallback only.** The client API base is derived at **runtime** by `env.ts` (browser → `window.location.origin` → same-origin `/api/*` proxy; server → `API_ORIGIN`), so this is no longer the production source of the URL and is no longer a deploy build-arg. Kept as the Zod default for local `pnpm dev`/tests. See `frontend-patterns.md` § Same-origin API proxy. |
| `PUBLIC_POSTHOG_KEY` | no | unset | Client-side PostHog project key |
| `PUBLIC_POSTHOG_HOST` | no | `https://eu.posthog.com` | PostHog ingestion host (EU region default) |
| `PUBLIC_SENTRY_DSN` | no | unset | Browser Sentry project |
| `PUBLIC_TURNSTILE_SITE_KEY` | no | unset | Cloudflare Turnstile site key for the scan-submit human gate (`TurnstileGate`). Unset → the verification modal is skipped and scans submit directly (preserves dev UX). Paired with the backend `TURNSTILE_SECRET_KEY`. Non-prod uses the always-pass test site key `1x00000000000000000000AA`. **Delivery:** `PUBLIC_*` is inlined into the Astro bundle at **build time**, so it is baked in the webapp Docker image: the deploy workflow passes it as a `--build-arg` (`webapp/Dockerfile` `ARG PUBLIC_TURNSTILE_SITE_KEY`) sourced from the GH Actions secret **`TURNSTILE_PUBLIC_SITE_KEY`** (the secret is `TURNSTILE_`-grouped for the secrets list; the build-arg + env-var name stays `PUBLIC_`-prefixed because Astro only inlines `PUBLIC_*` — renaming the build-arg would disable the gate). One image is shared by staging + prod, so the Cloudflare widget must list both hostnames. Setting it only as a Fly runtime secret would NOT work (the value is needed at `pnpm build`). |
| `RESEND_API_KEY` | no | unset | Outbound email (Resend) — server-only, NOT `PUBLIC_*`. Single verified sending domain `notifications.openlatch.ai` (shared with OpenLatch, cost decision 2026-05-28). Hardcoded `From:` in the send-call: `SaferSkills <<purpose>@notifications.openlatch.ai>`. Reply-to is a `@openlatch.ai` mailbox. |

## `.env.example` discipline

- **Every required var is documented** in the matching `.env.example` with a placeholder (`<set-me>` or a public-safe default).
- **No real secrets in `.env.example`** — `gitleaks` pre-commit hook enforces.
- **The example is the contract** — adding a runtime read of an undocumented var is rejected in review.

## Loading rules

- **Backend**: `pydantic-settings` reads from process env, then `.env` in dev. The `Settings` class is a frozen singleton (`@lru_cache`) imported as `from app.core.config import settings`. No re-instantiation, no override outside tests.
- **Frontend**: Astro reads `PUBLIC_*` vars at build time; `webapp/src/env.ts` re-exports a Zod-validated object. Components import `env` from there.
- **Tests**: backend tests override settings via `monkeypatch` on the singleton — never via raw `os.environ.setdefault`.

## Fly secret-staging rule (when deploy ships W2-W3)

When prod deploys land:

- **Always** use `flyctl secrets set --stage` followed by `flyctl deploy` in one job (per `ci-cd.md`). Never `flyctl secrets set` without `--stage` — that triggers an immediate roll that can apply new-shape secrets to a stale image.
- **Never split** `sync-secrets-*` from `deploy-*`. One atomic image-and-secrets roll per service per deploy.
- See `ci-cd.md` § Deployment for the full atomic-roll contract.

## Local dev (`docker-compose.yml`)

- Single compose file at repo root brings up postgres + api + webapp.
- Compose reads `.env` (gitignored) for dev overrides; the example lives at `.env.example` (committed).
- Override file `docker-compose.override.yml.example` shows how to point compose at an alternate Postgres / a local Resend stub.

## Hard rules

1. **Typed access only.** `app.core.config.settings` (backend) and `webapp/src/env.ts` (frontend) are the only entry points. No direct `os.environ` / `process.env` / `import.meta.env` outside those modules.
2. **`.env.example` is the contract.** New env var = new entry in the matching `.env.example` in the same PR.
3. **`PUBLIC_*` prefix means client-exposed.** Anything else is server-only. The Astro convention is non-negotiable.
4. **Fly secret-staging** when deploy lands. Never `flyctl secrets set` without `--stage` on production.

## When to update this rule

| Change | Updates here |
|---|---|
| New backend env var | "Backend" table + `services/api/.env.example` + `services/api/app/core/config.py` |
| New frontend env var | "Frontend" table + `webapp/.env.example` + `webapp/src/env.ts` |
| New secret stored in Fly | "Fly secret-staging rule" + `ci-cd.md` Deployment |
| New compose service | "Local dev" + root `docker-compose.yml` + `tech-stack.md` |
