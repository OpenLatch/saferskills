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

### Agent-pack test IDs (`AS-NN`) — a separate taxonomy

`rubric/AGENT/` (I-5.5) is a **separate pack tree** from the component rules above, with its own id grammar: `AS-NN` (regex `^AS-\d{2}$`, e.g. `AS-01` … `AS-22`). These are behavioral-test ids validated against `schemas/agent-pack-test.schema.json`, **not** rubric-rule ids — the `SS-<CATEGORY>-<NAME>-NN` grammar does **not** apply to them, and `generate-methodology.cjs` excludes `rubric/AGENT/` from the component rule walk. The agent-pack generator (step 9) is the only consumer.

## Catalog slugs

One catalog_item = one capability (Skill/MCP/Hook/Plugin/Rules); several capabilities can share one GitHub repo. The slug is the `/items/<slug>` permalink key and stays UNIQUE.

- **Per-capability slug**: `<org>--<repo>--<kind>-<name>[-<hash6>]` (e.g. `acme--devtools-agent-kit--skill-pdf-extract`). `<kind>` is the `catalog_item.kind` enum with underscores hyphenated (`mcp_server` → `mcp-server`, since the grammar disallows `_`); `<name>` is slugified; same-`(kind, name)` collisions within a repo get a `-<hash6>` of the capability's `component_path` (allocated in `app.scan.discovery`).
- **Public upload slug** (I-3.5): `upload--<arthash8>--<kind>-<name>` — `<arthash8>` is `scan_runs.content_hash_sha256[:8]` (no repo coordinates for an upload). Built in `app/scan/persistence.py::upload_capability_slug`.
- **Unlisted shadow slug** (I-3.5): `unlisted--<run8>--<kind>-<name>` — `<run8>` is `str(run_id)[:8]`. Per-run shadow rows are never served from the public catalog. Built in `app/scan/persistence.py::unlisted_capability_slug`.
- **Legacy repo-level slug** `<org>--<repo>` stays valid — the grammar was **widened, not replaced**: `^[a-z0-9][a-z0-9-]*(--[a-z0-9][a-z0-9-]*)+$`. Source: `schemas/catalog-item.schema.json` (flows to generated Pydantic/Zod/TS). Built in `app/scan/persistence.py::capability_slug`. The upload + unlisted slugs above satisfy this **same** grammar — **no regex change** (the `mcp_server` → `mcp-server` hyphenation still applies, since the grammar disallows `_`).

## Severity tiers

Rules and findings use a 5-tier severity ladder (locked decision D-02):

```
info | low | medium | high | critical
```

`info` carries weight 0 — advisory only; surfaces in the scan trace but does not affect the score. See `.claude/rules/methodology.md` § Sub-scores and aggregate for the per-tier penalty ranges and critical-floor application.

## Agent identifiers (single source of truth)

The closed set of coding-agent ids (`claude-code`, `cursor`, `codex`, `copilot`, `windsurf`, `cline`, `gemini`, `openclaw`) has **exactly one Python source of truth: `app/services/agent_compat.py`** — the `AgentName` Literal (for static typing) and `ALL_AGENTS = get_args(AgentName)` (the runtime tuple, derived so the two can never drift). The `other` runtime fallback (telemetry/agent-scan) is `AgentName | Literal["other"]` / `frozenset(ALL_AGENTS) | {"other"}`.

**Hard rule: never re-declare the agent-id list in Python.** Any module needing the set — a Pydantic DTO, a closed-enum type, a PostHog event guard, a membership check — MUST import `AgentName` / `ALL_AGENTS` from `app.services.agent_compat`. A hand-typed `Literal["claude-code", "cursor", …]` or a `frozenset({...})` of agent ids anywhere else is a guardrail violation (it silently drifts when an agent is added). Current correct consumers: `app/observability/events.py` (`InstallAgent`/`AgentRuntime`/`_RUNTIME_VALUES`), `app/schemas/agent_scan.py`, `app/schemas/installs.py`, `app/ingestion/framework/classifier.py`.

**The only permitted duplicates are cross-language / cross-boundary mirrors**, which cannot import the Python module and so re-declare the set explicitly — each MUST carry a `# Mirrors app/services/agent_compat.py::AgentName / ALL_AGENTS` comment and stay in lockstep:
- `schemas/catalog-item.schema.json::agentCompatibility` (JSON Schema → drives the generated Pydantic/Zod/TS).
- `app/models/install_event.py::AGENT_VALUES` (the native PG `agent` enum values).
- Alembic migrations that `CREATE TYPE`/backfill the enum (immutable snapshots — never edited after merge).
- `cli/src/agents/detect.rs` (the Rust install CLI).

Adding/renaming an agent = update `agent_compat.AgentName` **first**, then propagate to each mirror above (+ a migration for the PG enum) in the same PR.

## When to update this rule

| Change | Updates here |
|---|---|
| New generator step that produces a serialized key | "API JSON Body Keys" table |
| New paginated list envelope shape | "Hard rules" — never break the `data` key contract |
| New `<CATEGORY>` for scan rules | "Rule IDs" regex + `methodology.md` + `schemas/rubric-rule.schema.json` + `schemas/finding.schema.json` |
| Agent-pack test-ID grammar change | "Agent-pack test IDs" + `schemas/agent-pack-test.schema.json` + `scripts/generate-agent-pack.cjs` |
| New severity tier | "Severity tiers" + `methodology.md` § Sub-scores and aggregate + `schemas/rubric-rule.schema.json` + `schemas/finding.schema.json` |
| New / renamed coding agent | "Agent identifiers" — `app/services/agent_compat.py::AgentName` FIRST, then every documented mirror (catalog-item schema, `install_event.AGENT_VALUES`, migration `CREATE TYPE`, `cli/src/agents/detect.rs`) + a PG-enum migration |
| New DB-naming exception | "Database" |
| Catalog slug grammar change | "Catalog slugs" + `schemas/catalog-item.schema.json` regex + `app/scan/persistence.py::capability_slug` |
| New slug variant (e.g. upload / unlisted) | "Catalog slugs" + the builder in `app/scan/persistence.py` — confirm it satisfies the existing widened grammar |
