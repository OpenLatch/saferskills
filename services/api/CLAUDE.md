# CLAUDE.md — services/api

FastAPI backend for the SaferSkills public catalog + scan engine.

## W1 surface

- `GET /api/v1/health` — liveness + version + git_sha
- `GET /openapi.json` — captured by the codegen pipeline; consumed by the TS DTO generator

That's the entire shipped surface at W1. Everything else (catalog list, scan submit, scan report read) lands W2-3 via Track A/B.

## Post-W1 routes

- `GET /api/v1/items` / `/items/{slug}` / `/items/facets` — catalog browse (Track B).
- `GET|POST /api/v1/scans` + `/scans/{id}` + `/scans/{id}/events` — scan list/submit/report/SSE (Track B).
- `POST /api/v1/scans/upload` — upload a capability file / `.zip` (≤10 MiB) → scan it as a second front-end to the same engine (I-3.5). `GET|DELETE /api/v1/scans/r/{token}` + `POST /api/v1/scans/r/{token}/promote` — unlisted capability-URL view / delete / promote-to-public (anti-leakage headers, generic 404, `private_lookup` cap). `GET /items` gains an `artifact_source` (github|upload) filter; all public catalog/feed queries hard-filter `visibility='public'`.
- `GET /api/v1/stats` — homepage platform metrics (catalog size, registries, tier mix, median score, scan latency, `rule_count`, agents, `github_stars`). 60s in-process TTL cache + `Cache-Control: s-maxage=60, stale-while-revalidate=300`. Shared aggregate SQL lives in `app/queries.py`; the GitHub-stars proxy (`app/services/github_stars.py`) caches one hourly `api.github.com` call. Backs the live-with-fallback homepage (`webapp` `getHomepageData`).

## Conventions

- **Response models inherit `OrmBaseModel`** — `app/schemas/orm_base.py`. Never plain `BaseModel`. (`.claude/rules/naming-conventions.md`)
- **Paginated arrays use `data` not `items`** — same rule.
- **All env vars via `app/core/config.py`** — never `os.environ` directly. (`.claude/rules/environment-config.md`)
- **No detection logic in this layer at W1** — the scan engine is its own package (`app/scan/`) landing W2.

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
