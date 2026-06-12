# services/worker

The deployed **ingestion + bulk-scan worker** — a config-only deploy unit. There
is **no code here**: the worker runs the exact same Docker image as the API
(`services/api/Dockerfile`) with a different command, `python -m app.worker_main`.

## Why a separate process

The API and the Procrastinate worker used to run in one process. The worker's
ingestion crawls + bulk scan jobs are memory-heavy; sharing a process (and a
512 MB machine) with the web tier is what produced the staging OOM-loop. Splitting
them lets each be sized independently and means a worker OOM never takes the API
(or `/health`) down with it. The API tier deploys with
`INGESTION_WORKER_ENABLED=false` (in `services/api/fly.*.toml`); this app sets it
`true`.

Local dev + `docker compose up` are unchanged — there `INGESTION_WORKER_ENABLED`
keeps its default (`true`), so everything still runs in one process.

## What runs where

| Runs in the **worker** (`app.worker_main`) | Stays in the **API** (`app.main`) |
|---|---|
| Procrastinate worker: ingest queues + `scan` queue + periodic tasks | HTTP routes, SSE, the interactive `POST /scans` (asyncio.create_task) |
| Boot reapers (`recover_stale_scans`, `recover_stale_ingestion_runs`) | Migrations (`run_startup`) — also run here; advisory-locked, race-safe |
| | Unlisted-expiry **sweep loop** (advisory lock `0x5AFE5C12`) |
| | The Procrastinate **connector** (opened so the API's defer paths work) |

Both processes run migrations on boot (idempotent under lock `0x5AFE5C11`); the
worker exits non-zero if the DB is unmigrated and lets Fly's `[restart]` retry
(it has no HTTP surface, so no degraded-mode serving).

## Deploy

Deployed by `.github/workflows/deploy.yml` (`deploy-staging-worker` /
`deploy-production-worker`) against `registry.fly.io/saferskills-api:main-<sha>` —
the same image bytes as the API, never a separate build. The deploy job stages the
boot-guard secrets (see below) then `flyctl deploy --config fly.<env>.toml --image …`.

## Secrets (one-time operator setup)

The worker loads the same `Settings`, so `ENV=staging|production` hard-fails boot
without the four guard secrets. `deploy.yml` stages these via `flyctl secrets set
--stage`: `TURNSTILE_SECRET_KEY`, `SAFERSKILLS_CLI_POW_SECRET`,
`SAFERSKILLS_AGENT_MASTER_KEY`, `SAFERSKILLS_PACK_SIGNING_KEY` (+ `SENTRY_DSN`,
`POSTHOG_PROJECT_KEY`, `POSTHOG_SERVER_KEY`, `SLACK_ALERTS_WEBHOOK_URL`). The
HTTP-route-only `SAFERSKILLS_ADMIN_KEY` / `SAFERSKILLS_PROXY_SHARED_SECRET` are
**not** set here.

Not staged by CI (set once manually, as on the API app): `DATABASE_URL`,
`GITHUB_APP_ID`, `GITHUB_APP_PRIVATE_KEY`, `GITHUB_APP_INSTALLATION_ID`.

```bash
# First-time app creation (operator):
flyctl apps create saferskills-worker-staging --org openlatch
flyctl secrets set --app saferskills-worker-staging \
  DATABASE_URL=… GITHUB_APP_ID=… GITHUB_APP_PRIVATE_KEY=… GITHUB_APP_INSTALLATION_ID=…
# saferskills-worker (prod) is created later and kept suspended until MVP.
```

## Memory budget

`worker RSS ≈ ~200 MB baseline + SCAN_MAX_CONCURRENCY × (~40 MB per scan job) +
INGESTION_WORKER_CONCURRENCY × (~25-item batch incl. metadata_files)`. Staging runs
`2 + 2` to fit the 512 MB box (see `.claude/rules/ingestion.md` § memory budget).
`memory.rss_mb` is logged per scan job + ingestion cycle for headroom tracking.
