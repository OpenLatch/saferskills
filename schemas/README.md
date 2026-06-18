<div align="center">

<a href="../README.md">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="../webapp/public/logos/saferskills-dark-wordmark.svg">
    <img alt="SaferSkills" src="../webapp/public/logos/saferskills-light-wordmark.svg" height="38">
  </picture>
</a>

<h3>Data-contract schemas</h3>
<p>JSON Schema source-of-truth for every wire, DB, and type contract.</p>

</div>

## What it is

JSON Schema (draft 2020-12) source-of-truth for every data contract in SaferSkills. The schemas here are one of the two roots of the schema-driven pipeline (the other is FastAPI's `app.openapi()`); everything downstream — Pydantic models, SQLAlchemy models, TS DTOs, Zod validators — is generated, never hand-edited.

`pnpm run generate` runs **9 generators** that consume these files. Outputs land under:

- `services/api/app/schemas/generated/*.py` — Pydantic models
- `services/api/app/models/generated/*.py` — SQLAlchemy async ORM models (unless `x-postgresql-skip: true`)
- `services/api/openapi.json` — captured by booting the FastAPI app
- `services/api/app/generated/*.json` — backend mirrors (rule content, agent pack)
- `webapp/src/generated/openapi/types.gen.ts` — TS DTOs
- `webapp/src/generated/zod/*.ts` — Zod runtime validators
- `webapp/src/generated/methodology/*` — methodology MDX + rule tables

The full generator table (including the ingestion source-registry and rubric/agent-pack steps that read outside `schemas/`) lives in [`.claude/rules/schema-driven-development.md`](../.claude/rules/schema-driven-development.md). CI's `validate` lane fails on uncommitted output — the drift gate.

## Adding a schema

1. Write `schemas/<entity>.schema.json` with `$schema`, `$id`, `title`, `description`.
2. Run `pnpm run generate`.
3. Commit both the source schema **and** the generated output in the same commit.

## Conventions

- **Property names: camelCase** in the schema — the generators convert to snake_case for Python + the API JSON body (see [`.claude/rules/naming-conventions.md`](../.claude/rules/naming-conventions.md)).
- **`additionalProperties: false`** by default. Override only when an `x-` extension or metadata bag is genuinely open-ended.
- **`x-postgresql-skip: true`** skips SQLAlchemy emission (e.g. for `*-response` envelopes with no DB row); other `x-postgresql-*` extensions drive table name, enums, FKs, and indexes.

---

<sub>Part of **[SaferSkills](../README.md)** — every AI capability, independently scanned. · An [OpenLatch](https://openlatch.ai) project · [saferskills.ai](https://saferskills.ai)</sub>
