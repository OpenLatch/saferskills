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

Scan rules use the format `SS-<CATEGORY>-<NAME>-<NN>`:

- `SS-` prefix is fixed (distinguishes SaferSkills rules from any imported third-party detector vocabulary).
- `<CATEGORY>` is one of the closed set defined in `methodology.md` (`MCP`, `SKILL`, `RULES`, `HOOKS`, `PLUGIN`).
- `<NAME>` is uppercase kebab — `POISON-UNICODE`, `INJECT-FENCED-RUN`.
- `<NN>` is a two-digit zero-padded sequence, allocated in `rubric/<category>/<name>.md`.

Examples: `SS-MCP-POISON-UNICODE-01`, `SS-SKILL-INJECT-FENCED-RUN-02`, `SS-HOOKS-RCE-01`.

## When to update this rule

| Change | Updates here |
|---|---|
| New generator step that produces a serialized key | "API JSON Body Keys" table |
| New paginated list envelope shape | "Hard rules" — never break the `data` key contract |
| New `<CATEGORY>` for scan rules | "Rule IDs" + `methodology.md` |
| New DB-naming exception | "Database" |
