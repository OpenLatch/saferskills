# services/api — SaferSkills FastAPI backend

W1 shell. The scan engine, ingestion adapters, and catalog/report endpoints land via Initiatives I-02 / I-03 / I-04 starting W2.

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
├── main.py              # FastAPI app + lifespan + CORS + router wire-up
├── core/
│   ├── config.py        # pydantic-settings (env loader)
│   └── observability.py # Sentry + OTel init (no-op when env vars unset)
├── routers/
│   └── health.py        # GET /api/v1/health
├── models/
│   ├── base.py          # Declarative SQLAlchemy base
│   └── generated/       # ← codegen output (never hand-edit)
└── schemas/
    ├── orm_base.py      # OrmBaseModel for all response models
    └── generated/       # ← codegen output (never hand-edit)
migrations/              # Alembic stubs (no migrations yet)
tests/                   # pytest smoke
fly.staging.toml + fly.production.toml
Dockerfile
```

## See also

- `CLAUDE.md` (service-level) — architecture
- `../../.claude/rules/schema-driven-development.md` — codegen pipeline
- `../../.claude/rules/environment-config.md` — env var contract
