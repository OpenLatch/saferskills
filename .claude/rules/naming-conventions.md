# Naming Conventions

Biome (`biome.json`) enforces TS/React file + identifier naming via `useNamingConvention` and `useFilenamingConvention`; Ruff enforces the Python equivalents. The rules below are NOT covered by either linter — they are project-specific contracts that drift silently if not documented.

## API JSON Body Keys (Critical)

**API request and response bodies use snake_case keys.** Not camelCase.

JSON Schemas (`schemas/`) define properties in camelCase, but the generation pipeline converts them to snake_case for both backend and frontend:

| Layer | Key casing | Why |
|-------|-----------|-----|
| JSON Schema source files | camelCase | Schema convention |
| Python Pydantic fields | snake_case | `--snake-case-field` flag |
| Pydantic aliases | camelCase | Preserved from schema, suppressed on output |
| **API JSON responses** | **snake_case** | `OrmBaseModel.model_dump(by_alias=False)` |
| API JSON input | snake_case (camelCase also accepted) | `populate_by_name=True` on `OrmBaseModel` |
| Generated TS types | snake_case | `convertPropertiesToSnakeCase()` in `generate-types.cjs` |
| Generated Zod schemas | snake_case | `convertSchemaKeysToSnakeCase()` in `generate-zod.cjs` |

### Hard rules

- **All Pydantic response models must inherit `OrmBaseModel`** (`app/schemas/orm_base.py`), never plain `BaseModel`. Plain `BaseModel` serializes with camelCase aliases, breaking the frontend.
- **Paginated list responses use `"data"` as the array key** — never `"items"`. Both `PaginatedResponse` and `ListEnvelope` use `data: list[T]`. The frontend's `listEnvelopeSchema()` and all hand-written response types expect `"data"`.
- When writing frontend API types or Zod schemas by hand, use snake_case keys: `artifact_kind`, `rule_id`, `rubric_version`.
- When writing example JSON payloads in docs or plans, use snake_case: `{ "artifact_kind": "skill", "rule_id": "SS-SKILL-INJECT-01" }`.

## Database

Linters can't enforce DB naming — these are project conventions:

- Tables: snake_case, **plural** — `artifacts`, `findings`, `vendor_appeals`.
- Foreign keys: `<singular_table>_id` — `artifact_id`, `finding_id`.
- Indexes: `idx_<table>_<columns>` — `idx_artifacts_repo_url`.
- Constraints: `uq_<table>_<columns>`, `chk_<table>_<condition>`.

## API Endpoints

- RESTful, kebab-case, versioned: `/api/v1/artifacts`.
- Collections: plural nouns — `GET /api/v1/artifacts`.
- Resources: `GET /api/v1/artifacts/:id`.
- Non-CRUD actions: `POST /api/v1/artifacts/:id/rescan`.
- Query params: camelCase — `?artifactKind=skill&severity=high`.

## Rule IDs

Scan rules use the format `SS-<CATEGORY>-<NAME>-<NN>` (locked decision D-03):

- `SS-` prefix is fixed (distinguishes SaferSkills rules from any imported third-party detector vocabulary).
- `<CATEGORY>` is one of the closed set defined in `methodology.md` (`MCP`, `SKILL`, `RULES`, `HOOKS`, `PLUGIN`).
- `<NAME>` is uppercase kebab — `POISON-UNICODE-TAG`, `INJECT-FENCED-RUN`, `RCE-CURL-PIPE`.
- `<NN>` is a two-digit zero-padded sequence, allocated in `rubric/<CATEGORY>/<NAME>-NN.md`.

Examples: `SS-MCP-POISON-UNICODE-TAG-01`, `SS-SKILL-INJECT-FENCED-RUN-02`, `SS-HOOKS-RCE-CURL-PIPE-01`.

The regex (validated in `schemas/rubric-rule.schema.json` + `schemas/finding.schema.json`):

```
^SS-(MCP|SKILL|RULES|HOOKS|PLUGIN)-[A-Z][A-Z0-9-]*-\d{2}$
```

## Catalog slugs

One catalog_item = one capability (Skill/MCP/Hook/Plugin/Rules); several capabilities can share one GitHub repo. The slug is the `/items/<slug>` permalink key and stays UNIQUE.

- **Per-capability slug**: `<org>--<repo>--<kind>-<name>[-<hash6>]` (e.g. `acme--devtools-agent-kit--skill-pdf-extract`). `<kind>` is the `catalog_item.kind` enum with underscores hyphenated (`mcp_server` → `mcp-server`, since the grammar disallows `_`); `<name>` is slugified; same-`(kind, name)` collisions within a repo get a `-<hash6>` of the capability's `component_path` (allocated in `app.scan.discovery`).
- **Legacy repo-level slug** `<org>--<repo>` stays valid — the grammar was **widened, not replaced**: `^[a-z0-9][a-z0-9-]*(--[a-z0-9][a-z0-9-]*)+$`. Source: `schemas/catalog-item.schema.json` (flows to generated Pydantic/Zod/TS). Built in `app/scan/persistence.py::capability_slug`.

## Severity tiers

Rules and findings use a 5-tier severity ladder (locked decision D-02):

```
info | low | medium | high | critical
```

`info` carries weight 0 — advisory only; surfaces in the scan trace but does not affect the score. See `.claude/rules/methodology.md` § Sub-scores and aggregate for the per-tier penalty ranges and critical-floor application.

## When to update this rule

| Change | Updates here |
|---|---|
| New generator step that produces a serialized key | "API JSON Body Keys" table |
| New paginated list envelope shape | "Hard rules" — never break the `data` key contract |
| New `<CATEGORY>` for scan rules | "Rule IDs" regex + `methodology.md` + `schemas/rubric-rule.schema.json` + `schemas/finding.schema.json` |
| New severity tier | "Severity tiers" + `methodology.md` § Sub-scores and aggregate + `schemas/rubric-rule.schema.json` + `schemas/finding.schema.json` |
| New DB-naming exception | "Database" |
| Catalog slug grammar change | "Catalog slugs" + `schemas/catalog-item.schema.json` regex + `app/scan/persistence.py::capability_slug` |
