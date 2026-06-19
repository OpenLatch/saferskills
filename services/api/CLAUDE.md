# CLAUDE.md — services/api

FastAPI backend for the SaferSkills public catalog + scan engine.

## Process entrypoints

This package ships two entrypoints from one image:
- **`app.main:app`** — the uvicorn web tier (HTTP, SSE, interactive scans). Deployed with `INGESTION_WORKER_ENABLED=false`, so it does NOT run the Procrastinate worker, but it still opens the connector so its own defer paths work.
- **`python -m app.worker_main`** — the standalone Procrastinate worker (ingest queues + bulk `scan` queue + periodic tasks + boot reapers). Deployed as the separate `services/worker/` Fly app. Locally + in `docker compose up`, the worker runs in-process in the web lifespan (the `INGESTION_WORKER_ENABLED=true` default). See `.claude/rules/ingestion.md` § Procrastinate worker.

## Routes

- `GET /api/v1/health` — liveness + version + git_sha
- `GET /openapi.json` — captured by the codegen pipeline; consumed by the TS DTO generator

That's the entire shipped surface at W1. Everything else (catalog list, scan submit, scan report read) lands W2-3 via Track A/B.

## Post-W1 routes

- `GET /api/v1/items` / `/items/{slug}` / `/items/facets` — catalog browse (Track B).
- `GET|POST /api/v1/scans` + `/scans/{id}` + `/scans/{id}/events` — scan list/submit/report/SSE (Track B).
- `POST /api/v1/scans/upload` — upload one capability file, one `.zip`, or N loose files (combined ≤10 MiB) → scan it as a second front-end to the same engine (I-3.5). A **flat** multi-file upload (top-level files, no subdirectories) fans into one capability per file (`discover_capabilities(source_kind="upload")`) — even when one file is a recognized anchor like `SKILL.md` (which keeps its declared name); a structured `.zip` with subdirectories keeps normal discovery. The run report then renders per-file tabs; each `CapabilityRow` carries its own `manifest` + `download`. `GET|DELETE /api/v1/scans/r/{token}` + `POST /api/v1/scans/r/{token}/promote` — unlisted capability-URL view / delete / promote-to-public (anti-leakage headers, generic 404, `private_lookup` cap). `GET /items` gains an `artifact_source` (github|upload) filter; all public catalog/feed queries hard-filter `visibility='public'`.
- `GET /api/v1/community/slack/redirect` — 302 to the configured community Slack invite (`SLACK_INVITE_URL`; 503 when unset). Backs the webapp `/slack` pretty URL. A background health probe (`app/services/slack_invite_health.py`, advisory lock `0x5AFE5C14`) alerts via `SLACK_ALERTS_WEBHOOK_URL` + Sentry if the never-expire invite ever breaks.
- `GET /api/v1/stats` — homepage platform metrics (catalog size, registries, tier mix, median score, scan latency, `rule_count`, agents, `github_stars`). 60s in-process TTL cache + `Cache-Control: s-maxage=60, stale-while-revalidate=300`. Shared aggregate SQL lives in `app/queries.py`; the GitHub-stars proxy (`app/services/github_stars.py`) caches one hourly `api.github.com` call. Backs the live-with-fallback homepage (`webapp` `getHomepageData`).

## Conventions

- **Response models inherit `OrmBaseModel`** — `app/schemas/orm_base.py`. Never plain `BaseModel`. (`.claude/rules/naming-conventions.md`)
- **Paginated arrays use `data` not `items`** — same rule.
- **All env vars via `app/core/config.py`** — never `os.environ` directly. (`.claude/rules/environment-config.md`)
- **No detection logic in this layer** — the scan engine is its own package (`app/scan/`).

## When you add a router

1. Write the schema → `pnpm run generate` → commit both files
2. Add the router under `app/routers/<entity>.py`
3. Register it in `app/main.py` with the canonical `/api/v1` prefix
4. Add a happy-path + an adversarial-input test under `tests/`

## When you add a model

- The JSON Schema source-of-truth is `schemas/<entity>.schema.json` at the repo root
- The Pydantic + SQLAlchemy generators emit under `app/{schemas,models}/generated/`
- Inherit user-facing response models from `OrmBaseModel`

## Database

Alembic is wired (`alembic.ini` + `migrations/env.py`). Migrations **auto-apply in-process on every API boot** in all environments: the FastAPI lifespan calls `app/core/startup.py::run_startup`, which runs `alembic upgrade head` under a `pg_advisory_lock` (race-safe across concurrent Machines) with retry/backoff, and falls back to degraded mode (503 on every route but `/api/v1/health`) if the DB is unreachable. No Fly `release_command`, no manual migrate step. See `.claude/rules/ci-cd.md` § Deployment.
