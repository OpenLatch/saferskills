---
paths:
  - "schemas/**"
  - "scripts/generate-*.cjs"
  - "services/api/app/schemas/**"
  - "services/api/app/models/**"
  - "webapp/src/generated/**"
  - "services/api/openapi.json"
---

# Schema-Driven Development

> **Paths**: `schemas/**`, `scripts/generate-*.cjs`, `services/api/app/schemas/**`, `services/api/app/models/**`, `webapp/src/generated/**`, `services/api/openapi.json`

## Purpose

Two sources of truth feed every wire / DB / type contract:

1. **JSON Schemas** under `schemas/<name>.schema.json` — entity shapes (what an `Artifact`, `Finding`, `Rule` looks like).
2. **FastAPI's `app.openapi()`** — endpoint DTOs (request / response shapes per route).

Everything downstream — Pydantic models, SQLAlchemy models, TS DTO types, Zod schemas, the Hey-API client — is **generated**. Generated code lives under any `generated/` directory and is **never edited manually**.

## The 7 generators (ordered)

`pnpm run generate` runs them in dependency order. Skipping a step risks drift; the CI `validate` lane catches a missed run.

| # | Step | Input | Output | Owner script |
|---|---|---|---|---|
| 1 | **validate** | `schemas/*.schema.json` | (none — fail fast on invalid schema) | `scripts/validate-schemas.cjs` (ajv-cli) |
| 2 | **pydantic** | `schemas/*.schema.json` | `services/api/app/schemas/generated/*.py` | `scripts/generate-pydantic.cjs` → `services/api/scripts/generate_pydantic_models.py` (datamodel-code-generator, per-file, `--base-class OrmBaseModel`) |
| 3 | **sqlalchemy** | `schemas/*.schema.json` (skip if `x-postgresql-skip: true`) | `services/api/app/models/generated/*.py` | `scripts/generate-sqlalchemy.cjs` → `services/api/scripts/generate_sqlalchemy_models.py` (Jinja2 + `KNOWN_ENUMS`, reads `x-postgresql-*`) |
| 4 | **openapi.json** | FastAPI app | `services/api/openapi.json` | `scripts/generate-openapi.cjs` (runs `app.openapi()`) |
| 5 | **ts-types** | `services/api/openapi.json` + `schemas/*.schema.json` | `webapp/src/generated/openapi/types.gen.ts` + `webapp/src/generated/schemas/*.ts` | `scripts/generate-ts-types.cjs` (snake_case conversion baked in) |
| 6 | **zod** | `schemas/*.schema.json` | `webapp/src/generated/zod/*.ts` | `scripts/generate-zod.cjs` (snake_case conversion baked in) |
| 7 | **methodology** | `rubric/<CATEGORY>/<NAME>-NN.md` (YAML frontmatter) | `webapp/src/generated/methodology/index.mdx` | `scripts/generate-methodology.cjs` (validates frontmatter against `schemas/rubric-rule.schema.json`; stamps rubricSha via `git log -n 1 -- rubric/`) |

## SQLAlchemy generation (`x-postgresql-*` + `KNOWN_ENUMS`)

The SQLAlchemy step is a Python generator ported from openlatch-platform
(`services/api/scripts/generate_sqlalchemy_models.py` + `scripts/templates/*.j2`),
invoked through the thin `scripts/generate-sqlalchemy.cjs` wrapper. It produces a
**full column projection** (not the retired W1 id/timestamps/metadata stub) — the
generated models under `app/models/generated/` ARE the production schema-backed
models, wired in via `app/models/__init__.py` and `app/models/_relationships.py`.
Details: `docs/codegen.md`.

- **Schema-level**: `x-postgresql-tablename`, `x-postgresql-classname` (ORM class
  name when it differs from `title`, e.g. `ScanReport`→`Scan`), `x-postgresql-skip`
  (wire-only — no table), `x-postgresql-indexes`, `x-postgresql-extra-columns`
  (DB columns absent from the wire shape — FKs, idempotency keys, timestamps …).
- **Field-level**: `x-postgresql-enum-type`, `x-foreign-key` (`{table, column,
  ondelete}`), `x-primary-key`, `x-postgresql-unique`, `x-postgresql-default`,
  `x-postgresql-nullable` (override), `x-postgresql-type` (`TEXT`/`BYTEA`/…).
- **Enums are native PG types**. Every `x-postgresql-enum-type` must be registered
  in `KNOWN_ENUMS` (in the generator) with its closed value set; the generator
  hard-fails on an unregistered enum. `_base.py` emits `<NAME>_VALUES` tuples +
  `<name>_enum = sa.Enum(*VALUES, native_enum=True, create_type=False)`. A new or
  changed enum needs **both** a `KNOWN_ENUMS` entry **and** an Alembic migration
  that runs `CREATE TYPE … AS ENUM` (the generator never emits DDL). The six
  schema-backed tables use native enums; the internal hand-written tables
  (`item_sources.registry_id`, `rate_limits.bucket`) stay VARCHAR+CHECK.

## Adding a new schema

1. Write `schemas/<name>.schema.json` — camelCase properties per the JSON Schema convention. Add `x-postgresql-*` extensions (above) if it backs a table; register any new enum in `KNOWN_ENUMS` + ship a `CREATE TYPE` migration.
2. Run `pnpm run generate`.
3. Commit BOTH the schema source AND the generated files. The CI drift gate diffs after a fresh regenerate and fails on any delta.
4. If the schema is a wire-only shape (never persisted), add `x-postgresql-skip: true` at the top level — the SQLAlchemy generator skips it.

## Adding a new endpoint DTO

1. Write the Pydantic request/response model in `services/api/app/schemas/` (hand-written models are allowed at this layer — they are non-generated wrappers around generated entity shapes).
2. Mount the route on its router; the response_model points at the Pydantic class.
3. Run `pnpm run generate` — steps 4 + 5 pick up the new endpoint and regenerate `openapi.json` + `types.gen.ts`.
4. Commit the route + the regenerated outputs.

## Hard rules

1. **`generated/` is read-only to humans.** The pre-commit hook `block-generated.sh` rejects any commit that modifies a path matching `**/generated/**` without a corresponding generator-source change in the same commit.
2. **The CI drift gate is non-negotiable.** PR `validate` lane runs `pnpm run generate && git diff --exit-code`; non-zero diff fails the check. This catches hardcoded enum values, stale generated models, and Python-vs-TS drift in one shot.
3. **All Pydantic response models inherit `OrmBaseModel`** (cf. `naming-conventions.md`). Generated Pydantic classes already do; hand-written ones must.
4. **Paginated responses use `data: list[T]`** — never `items`. The frontend's `listEnvelopeSchema()` and every hand-written response type expect `"data"`.
5. **No camelCase in the wire.** The generators convert camelCase schema properties to snake_case for both backend and frontend. If a generated file shows camelCase keys, the conversion broke — fix the generator, never hand-edit.
6. **Generators run in order.** `openapi.json` (step 4) depends on the Pydantic models (step 2); `ts-types` (step 5) depends on `openapi.json`. Running them out of order produces inconsistent outputs.

## When to update this rule

| Change | Updates here |
|---|---|
| New generator added / removed | "The 7 generators" table + `pnpm run generate` script + `scripts/_run-generators.cjs` |
| New schema convention (e.g. another `x-postgresql-skip`-style extension) | "Adding a new schema" |
| Generator output path changed | The table + `generated-code.md` |
| New CI lane around codegen | `ci-cd.md` Pipeline lanes + the drift-gate description here |
