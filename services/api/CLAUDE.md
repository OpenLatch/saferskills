# CLAUDE.md — services/api

FastAPI backend for the SaferSkills public catalog + scan engine.

## W1 surface

- `GET /api/v1/health` — liveness + version + git_sha
- `GET /openapi.json` — captured by the codegen pipeline; consumed by the TS DTO generator

That's the entire shipped surface at W1. Everything else (catalog list, scan submit, scan report read) lands W2-3 via Track A/B.

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

Alembic is wired (`alembic.ini` + `migrations/env.py`) but holds **zero migrations** at W1. The first migration lands with the catalog ingestion in W2.
