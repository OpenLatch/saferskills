---
paths:
  - "**/generated/**"
  - "services/api/openapi.json"
---

# Generated Code

> **Paths**: `**/generated/**`, `services/api/openapi.json`

## Hard rule

**Never edit generated files by hand.** Run the generator that produces them.

Generated paths at W1:

- `services/api/app/schemas/generated/` — Pydantic models (from `schemas/*.schema.json`)
- `services/api/app/models/generated/` — SQLAlchemy models (from `schemas/*.schema.json`)
- `services/api/openapi.json` — FastAPI OpenAPI export (from `app.openapi()`)
- `webapp/src/generated/openapi/types.gen.ts` — TS DTO types (from `openapi.json`)
- `webapp/src/generated/schemas/*.ts` — Per-schema TS types (from `schemas/*.schema.json`)
- `webapp/src/generated/zod/*.ts` — Zod schemas (from `schemas/*.schema.json`)
- `services/api/app/ingestion/config/generated/source_registry.py` — ingestion provider registry `SOURCE_NAMES`/`REGISTRY_IDS`/`SOURCE_HOSTS`/`ALL_HOSTS` (from `config/sources/*.yaml`). Its generator (STEP 0) also rewrites the `source.enum` / `…registryId.enum` arrays inside `schemas/ingestion-event.schema.json` + `schemas/catalog-item.schema.json` in place — so those two enum arrays are generator-managed too (edit the YAMLs, not the JSON). See `ingestion.md`.

The pre-commit hook `block-generated.sh` rejects any commit that modifies a `**/generated/**` path without a same-commit edit to the corresponding generator source. The CI `validate` lane runs `pnpm run generate && git diff --exit-code` and fails on any drift.

## How to update generated code

1. Edit the source — a JSON Schema under `schemas/`, a Pydantic model under `services/api/app/schemas/`, or a router that affects `openapi.json`.
2. Run `pnpm run generate`.
3. Commit both the source change AND the regenerated outputs in one PR.

Full pipeline + per-generator detail: `schema-driven-development.md`.

## When to update this rule

| Change | Updates here |
|---|---|
| New generated output path added | "Generated paths at W1" list + `schema-driven-development.md` |
| Generator block-script change | This rule + `schema-driven-development.md` Hard rules |
