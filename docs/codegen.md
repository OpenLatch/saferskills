# Codegen — schema → Pydantic + SQLAlchemy + TS + Zod

SaferSkills generates every wire / DB / type contract from two sources of truth:
JSON Schema (`schemas/*.schema.json`) for entity shapes and FastAPI's
`app.openapi()` for endpoint DTOs. `pnpm run generate` runs the seven generators
in order (validate → pydantic → sqlalchemy → openapi.json → ts-types → zod →
methodology). Generated code under any `generated/` directory is **never edited
by hand**; the CI `validate` lane runs `pnpm run generate && git diff --exit-code`
and fails on drift. Full pipeline reference: `.claude/rules/schema-driven-development.md`.

This doc covers the **Python codegen** for the Pydantic + SQLAlchemy steps,
ported from openlatch-platform's mature generator (D-REPAIR-01) to retire the W1
stub that emitted only `id / created_at / updated_at / metadata` per class.

## Layout

| File | Role |
|---|---|
| `services/api/scripts/generate_pydantic_models.py` | Drives `datamodel-code-generator` **per schema file** → `app/schemas/generated/<stem>.py`, inheriting `OrmBaseModel` (snake_case wire format). |
| `services/api/scripts/generate_sqlalchemy_models.py` | Walks `schemas/`, reads `x-postgresql-*` extensions, renders ORM models via Jinja2 → `app/models/generated/`. |
| `services/api/scripts/templates/base.py.j2` | Renders `_base.py` — re-exports the shared `Base` + the native-enum objects. |
| `services/api/scripts/templates/sqlalchemy_model.py.j2` | Renders one ORM model per table. |
| `scripts/generate-{pydantic,sqlalchemy}.cjs` | Thin Node wrappers (`uv run python …`) so the existing `_run-generators.cjs` orchestrator is unchanged. |

> **Divergences from openlatch-platform** (single-repo + existing JS pipeline):
> the upstream client-schemas materialization branch is dropped; the orchestrator
> stays the `_run-generators.cjs` chain (no `generate_models.py`); openapi export
> stays `generate-openapi.cjs`; the Pydantic step runs **per-file** to keep module
> names stable; and TS/Zod keep SaferSkills' snake_case `.cjs` generators.

## The generated SQLAlchemy models ARE production

The six schema-backed tables are generated (full column projection, native PG
enum columns) and wired in as the production models:

- `app/models/generated/` — `CatalogItem`, `Scan`, `Finding`, `ScanRun`,
  `VendorVerification`, `VendorResponse` (+ `_base.py`).
- `app/models/__init__.py` — imports the six generated models + the five internal
  hand-written ones (`ItemSource`, `RateLimit`, `UploadFile`, `ArtifactBlob`,
  `ScanEvent` — no JSON-Schema source) and the relationship layer.
- `app/models/_relationships.py` — attaches every `relationship()` (the generator
  emits FK columns only), preserving the cascade / passive_deletes semantics.
- `app/models/{catalog_item,scan,scan_run,vendor}.py` — back-compat re-export
  shims so `from app.models.scan import Scan` keeps working.

## `x-postgresql-*` extensions

**Schema-level:** `x-postgresql-tablename`, `x-postgresql-classname` (ORM class
name ≠ schema `title`, e.g. `scan-report.schema.json` title `ScanReport` → class
`Scan`), `x-postgresql-skip: true` (wire-only — no table), `x-postgresql-indexes`
(`{name, columns, unique?, where?}`), `x-postgresql-extra-columns` (DB columns the
wire shape omits — `{name, type, length?, nullable?, unique?, default?,
foreign_key?, enum_type?}`).

**Field-level:** `x-postgresql-enum-type`, `x-foreign-key` (`{table, column,
ondelete?}`), `x-primary-key`, `x-postgresql-unique`, `x-postgresql-default`
(SQL expr), `x-postgresql-nullable` (override the JSON-Schema-derived nullability),
`x-postgresql-type` (`TEXT` / `BYTEA` / `SMALLINT`), `x-postgresql-on-update`.

Wire-shaped report schemas (`scan-report`, `scan-run-report`) describe the table
mostly via `x-postgresql-extra-columns` + a few `x-postgresql-skip`'d nested/aliased
fields, while their `properties` still drive the Pydantic DTO.

## `KNOWN_ENUMS` + native enums (the contract)

Every `x-postgresql-enum-type` must be registered in `KNOWN_ENUMS` (in
`generate_sqlalchemy_models.py`) with its closed value set. The generator
**hard-fails** on an unregistered enum:

```
Unknown x-postgresql-enum-type 'mystery'. Register it in KNOWN_ENUMS in
scripts/generate_sqlalchemy_models.py before regenerating.
```

`_base.py` emits, per enum, a `<NAME>_VALUES` tuple + a
`<name>_enum = sa.Enum(*<NAME>_VALUES, name="<name>", native_enum=True,
create_type=False, create_constraint=False)`. `create_type=False` means **the
generator never emits DDL** — the Alembic migrations own every `CREATE TYPE …
AS ENUM`. The value tuples are the single source of truth shared by `_base.py`,
the migration `CREATE TYPE`, and (historically) the CHECK constraints.

## Adding / changing a schema or enum

1. Edit `schemas/<name>.schema.json` (camelCase props). For a table, add the
   `x-postgresql-*` extensions above.
2. **New or changed enum**: add/update its `KNOWN_ENUMS` entry **and** write an
   Alembic migration that `CREATE TYPE … AS ENUM` (or `ALTER TYPE … ADD VALUE`).
3. `pnpm run generate`.
4. Add a migration for any column/table change (the generator does not emit DDL).
5. Commit the schema source **and** the regenerated outputs together (the drift
   gate diffs after a fresh regenerate).

> On Windows the generators write CRLF; `.gitattributes` (`* text=auto eol=lf`)
> normalizes to LF on commit, so the Linux CI drift gate stays green. Use
> `git diff --ignore-all-space` locally if EOL noise obscures a diff.
