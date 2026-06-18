<div align="center">

<a href="../../README.md">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="../../webapp/public/logos/saferskills-dark-wordmark.svg">
    <img alt="SaferSkills" src="../../webapp/public/logos/saferskills-light-wordmark.svg" height="38">
  </picture>
</a>

<h3>API backend</h3>
<p>The FastAPI service — catalog, scan engine, ingestion, and report endpoints.</p>

</div>

## What it is

The FastAPI backend for the SaferSkills public catalog and scan engine. It ships **two entrypoints from one image**: `app.main:app` (the uvicorn web tier — HTTP, SSE, interactive scans) and `python -m app.worker_main` (the Procrastinate worker — ingestion + bulk scan, deployed separately as [`services/worker/`](../worker/README.md)). Locally and in `docker compose up` the worker runs in-process.

## Run locally

```bash
cd services/api
uv sync
uv run uvicorn app.main:app --reload
curl http://localhost:8000/api/v1/health
```

## Quality gates

```bash
uv run pytest tests/ -x         # tests
uv run ruff check . --fix       # lint
uv run ruff format .            # format
uv run pyright                  # type check
```

## Layout

```
app/
├── main.py            # FastAPI app + lifespan (migrations on boot, worker, sweeps)
├── worker_main.py     # standalone Procrastinate worker entrypoint
├── core/              # config, startup/migrations, middleware
├── observability/     # Sentry + PostHog + OTel (no-op when env unset)
├── routers/           # /api/v1/* — health, items, scans, agent-scans, admin, …
├── scan/              # the deterministic scan engine (discovery, fetch, scoring)
├── agent_scan/        # behavioral Agent Scan (pack signing, canaries, grading)
├── ingestion/         # YAML-driven catalog ingestion + Procrastinate tasks
├── queue/             # interactive scan runner (asyncio.create_task path)
├── services/          # cross-cutting services (turnstile, github stars, rate limits)
├── models/            # SQLAlchemy models (+ generated/ — never hand-edit)
├── schemas/           # Pydantic DTOs — OrmBaseModel (+ generated/)
└── db/                # session + engine
migrations/            # Alembic — auto-applied in-process on every boot
tests/                 # pytest
fly.staging.toml + fly.production.toml + Dockerfile
```

Migrations auto-apply in-process on every boot under a `pg_advisory_lock` (race-safe across Machines) — there is no Fly `release_command` and no manual migrate step.

## See also

- [`services/api/CLAUDE.md`](./CLAUDE.md) — entrypoints, routes, conventions
- [`../worker/README.md`](../worker/README.md) — the worker that shares this image
- [`.claude/rules/schema-driven-development.md`](../../.claude/rules/schema-driven-development.md) — codegen pipeline
- [`.claude/rules/environment-config.md`](../../.claude/rules/environment-config.md) — env var contract

---

<sub>Part of **[SaferSkills](../../README.md)** — every AI capability, independently scanned. · An [OpenLatch](https://openlatch.ai) project · [saferskills.ai](https://saferskills.ai)</sub>
