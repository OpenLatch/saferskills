# `schemas/`

JSON Schema (draft 2020-12) source-of-truth for every data contract in SaferSkills.

The 6 generators under `scripts/generate-*.cjs` consume these files. Generated outputs land under:
- `services/api/app/schemas/generated/*.py` — Pydantic models
- `services/api/app/models/generated/*.py` — SQLAlchemy async ORM models (unless `x-postgresql-skip: true`)
- `services/api/openapi.json` — captured by booting the FastAPI app
- `webapp/src/generated/openapi/types.gen.ts` — TS DTOs
- `webapp/src/generated/zod/*.ts` — Zod runtime validators

Run `pnpm run generate` after editing anything here. CI's `validate` lane fails on uncommitted output (the drift gate — see `.claude/rules/schema-driven-development.md`).

## Adding a schema

1. Write `schemas/<entity>.schema.json` with `$schema`, `$id`, `title`, `description`.
2. Run `pnpm run generate`.
3. Commit both the source schema AND the generated output in the same commit.

## Conventions

- Property names: camelCase in the schema (the generators convert to snake_case for Python + the API JSON body, per `.claude/rules/naming-conventions.md`).
- `additionalProperties: false` by default. Override only when an `x-` extension or metadata bag is genuinely open-ended.
- Use `x-postgresql-skip: true` to skip SQLAlchemy emission (e.g. for `*-response` envelopes that don't have a DB row).

## W1 status

Two seed schemas (`catalog-item.schema.json` + `scan-report.schema.json`) — deliberate placeholders to prove the codegen contract works end-to-end. Replaced by the real Track A/B shapes in W2.
