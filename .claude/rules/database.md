# Database

> **Paths**: `services/api/migrations/**`, `services/api/app/models/**`, `services/api/app/db/**`, `services/api/alembic.ini`

PostgreSQL 17, single store (no Redis — in-process LRU only, per `tech-stack.md`). SQLAlchemy 2 async (`AsyncSession` everywhere), Alembic for migrations. This rule lands with the first real content-storage subsystem: `artifact_blobs` (Phase B).

## Migrations

- **Auto-applied in-process on every API boot, every environment.** `app/core/startup.py::run_startup` runs `alembic upgrade head` under a session-level `pg_advisory_lock` (key `0x5AFE5C11`) — race-safe across concurrent Machines. No Fly `release_command`, no manual migrate step. See `.claude/rules/ci-cd.md` § Deployment.
- **One revision per schema change**, named `YYYY_MM_DD_NNNN_<slug>.py`, `down_revision` chained to the prior head.
- **Every migration is reversible** — `downgrade()` drops what `upgrade()` adds. Current head: `0015_install_events` (down-rev `0014_scan_pipeline_redesign`) — creates the dedicated `install_events` table + the native `agent` PG enum (the existing `kind` enum from `0009` is reused) backing the real opt-in `install_activity` aggregate (I-05, D-05-31); `idx_install_events_item_created (catalog_item_id, created_at DESC)`; `catalog_item_id` FK `ON DELETE CASCADE`; rows retained (redacted IP, no PII). `0014_scan_pipeline_redesign` (down-rev `0013_add_ingestion_runs`) — the collect-and-scan redesign: (a) `scan_source` enum += `rescan_rules`; (b) `catalog_items` collapses the two scan-depth recency columns (`last_deep_scan_at`/`last_lite_scan_at`, added by `0012`) into the unified queue-of-record set `last_scanned_at` + `scanned_rubric_version` + `scanned_engine_version` + `last_checked_at` (`last_scanned_at` is backfilled from the old columns BEFORE they drop — no data loss); (c) the NEW internal `repo_fetch_state` table (per-repo conditional-fetch validators). `0013_add_ingestion_runs` creates the `ingestion_runs` table (one row per cycle attempt) backing the eagle-eye health view (`GET /admin/sources` enrichment + `…/{source}/runs`); `status`/`trigger` CHECKs + `idx_ingestion_runs_source_started (source, started_at DESC)` + partial `idx_ingestion_runs_running WHERE status='running'`; swept after 90 days by `app/core/sweeps.py`. `0012_phase_c_scan_recency` added the nullable `catalog_items.last_deep_scan_at` + `last_lite_scan_at` recency columns (now collapsed by `0014`). Chain: `0015_install_events` ← `0014_scan_pipeline_redesign` ← `0013_add_ingestion_runs` ← `0012` (scan recency) ← `0011` (outbox tables) ← `0010` (full projection) ← `0009` (native enums) ← `0008`. Reversible downgrades throughout.
- Naming follows `.claude/rules/naming-conventions.md` § Database (plural snake_case tables, `idx_`/`uq_`/`chk_` constraints, `<singular>_id` FKs).
- **Models are codegen-driven (since `0009` / I-04 Phase A0).** The eight **schema-backed** models — the six original (`CatalogItem`, `Scan`, `Finding`, `ScanRun`, `VendorVerification`, `VendorResponse`) plus `IngestionEvent` + `MergeCandidate` (I-04) — are **generated** from `schemas/` into `app/models/generated/` (full column projection, native PG enum columns — see `schema-driven-development.md` § SQLAlchemy generation + `docs/codegen.md`). The **thirteen internal stores** with no JSON-Schema source and no wire DTO stay **hand-written** under `app/models/*.py`: `ItemSource`, `RateLimit`, `UploadFile`, `ArtifactBlob`, `ScanEvent`, `Author`, `CrawlerCursor`, `PopularityFormula`, `AccessLog`, `AdminAuditLog`, `IngestionRun`, `RepoFetchState`, `InstallEvent`. **Criterion**: a table with a JSON Schema that is serialized over the API is generated (Pydantic+Zod+TS+SQLAlchemy together — there is no DB-only codegen mode); a table never serialized over the API stays hand-written. All are registered + relationship-wired in `app/models/__init__.py` (+ `_relationships.py`) so `Base.metadata` sees every table.

## Native enum types (migration `0009`)

`0009_native_enum_types` converts the six schema-backed tables' enum columns from `VARCHAR(20) + CHECK` to **native PG enum types** (`kind`, `popularity_tier`, `tier`, `scan_source`, `scan_run_status`, `severity`, `sub_score`, `status_at_scan`, `vendor_verification_state`, `visibility`, `source_kind`) so the generated `sa.Enum(..., native_enum=True, create_type=False)` columns match the DB. The closed value sets are the single source of truth shared by `0009`, the original CHECK constraints, and `app/models/generated/_base.py`. A new/changed enum value = update all three + a migration. `item_sources.registry_id` + `rate_limits.bucket` are intentionally NOT converted (internal hand-written tables, no generated native-enum column).

## Per-capability scans (`scan_runs`)

One repo scan discovers + scores N capabilities (a Skill, an MCP server, hooks, …) and fans out to N `scans` rows grouped under one `scan_runs` row. This overturns the original *"one catalog_item per (github_org, github_repo)"* decision — **one catalog_item = one capability**, and several capabilities can share one repo URL. (Unlisted runs use per-run **shadow** catalog_items — see § Upload + visibility.)

| Piece | Shape | Role |
|---|---|---|
| `scan_runs` | `id` PK; `idempotency_key` UNIQUE; `github_url`/`ref_sha`; `repo_aggregate_score` (0–100 chk) + `repo_tier` (chk); `kind_tally` JSONB; `capability_count`; `rubric_version`/`engine_version`/`source` (chk)/`latency_ms`/`file_count`; `status` (chk); timestamps | The repo scan. `repo_aggregate_score` = rounded mean of its capability scores. `/scans/runs/<run_id>` is the repo report. |
| `scans.scan_run_id` | nullable FK → `scan_runs` (`SET NULL`) | Links a per-capability scan to its run. Backfilled 1:1 for legacy/seed scans. |
| `scans.component_path` | String(1024) nullable | Relative path of the scanned capability subtree (`null`/`""` = whole-repo). |
| `scan_events.scan_run_id` | nullable FK → `scan_runs` (`CASCADE`) | SSE progress re-keys onto the run (channel `scan_progress_<run_id>`); `scan_events.scan_id` is now nullable. |

- **`UNIQUE(catalog_items.github_url)` is dropped** (replaced with non-unique `idx_catalog_items_github_url`) — shared-repo capabilities need it. The slug UNIQUE stays; per-capability slug is `<org>--<repo>--<kind>-<name>[-<hash6>]` (see `naming-conventions.md` § slug grammar).
- **Discovery → fan-out** lives in `app/scan/discovery.py` (pure) + `app/scan/engine.py::run_repo_scan`; persistence in `app/scan/persistence.py::persist_completed_scan_run`. Snapshots/manifests are **per-capability subtree**.
- **Backfill (migration 0007):** one `scan_runs` row per existing `scans` row (each a 1-capability run, reusing the scan's idempotency_key). Removed capabilities on a rescan are **not deleted** (archived-public policy).

## Auto-scan queue-of-record (`catalog_items` recency + `repo_fetch_state`, migration 0014)

The durable auto-scan pipeline (`app/ingestion/tasks_scan.py`) uses **catalog_items as the queue-of-record** — there is no separate scan-queue table; the reconciliation drainer re-derives what to scan from these columns each tick. Migration 0014 collapsed the two scan-depth columns (`last_deep_scan_at`/`last_lite_scan_at`, deep/lite had no engine difference) into one change-gated set.

| Column | Role |
|---|---|
| `catalog_items.last_scanned_at` | When this capability was last scored (NULL = never scanned → coverage selection). |
| `catalog_items.scanned_rubric_version` / `scanned_engine_version` | The rubric/engine SHAs active at the last scan. A mismatch vs the current versions → the reconciliation drainer re-selects the repo for a **re-eval from stored bytes** (`source='rescan_rules'`, no GitHub re-crawl). |
| `catalog_items.last_checked_at` | When the repo ref was last resolved (200 **or** 304). A 304 / unchanged ref bumps this without a scan; `< now() - SCAN_FRESHNESS_DAYS` → a cheap periodic re-check. |

All four are stamped across **every public-github capability sharing the repo URL** on a completed scan (they move together). They are `x-postgresql-extra-columns` (DB-only — not on the wire DTO).

**`repo_fetch_state`** (hand-written internal store) holds the per-repo conditional-fetch validators so an unchanged repo costs a free 304 against the shared GitHub App-token budget:

| Column | Role |
|---|---|
| `github_url` PK | The per-repo key (catalog_items is per-capability, scan_runs per-run — neither is a stable per-repo home). |
| `etag` / `last_modified` | Sent as `If-None-Match` / `If-Modified-Since` on the next ref resolve. |
| `resolved_ref_sha` | HEAD commit SHA at the last resolve — the content-change signal (changed SHA → re-fetch + scan). |
| `last_checked_at`, `created_at`, `updated_at` | Bookkeeping. |

**Stale-run recovery (`recover_stale_scans`).** On boot, runs still `pending`/`running` past a 15-minute grace are flipped to `failed` — they're orphans of an interactive `POST /scans` (`asyncio.create_task`) dropped by a restart. The **durable** bulk path self-heals instead (Procrastinate retries the idempotent job + the reconciliation `last_scanned_at IS NULL` predicate re-selects anything unfinished), so recovery touches only the orphaned `scan_runs` rows, never the queue. Testable inner: `app/queue/scan_runner.py::mark_stale_runs_failed`.

## Stored artifact snapshots (`artifact_blobs`)

The stored-public-artifact-snapshot feature persists the raw bytes of scanned **text** files so the item page can render line-level version diffs and serve a SaferSkills-built `.zip`. Three pieces:

| Piece | Shape | Role |
|---|---|---|
| `artifact_blobs` | `sha256` (64-char hex) PK → `content` (bytea), `byte_size`, `is_binary`, `created_at` | Content-addressed dedup store. One row per unique file body across all scans/items. |
| `scans.file_hashes` | JSONB `{path → sha256 \| null}` | Per-scan snapshot manifest. `null` = the file is known-but-not-stored (binary / oversize sentinel). Joins a scan back to its blobs. |
| `catalog_items.content_hash_sha256` | 64-char hex | Stable identity of the whole snapshot (sha256 of the sorted `file_hashes` map). Enables future drift detection. |

### Contract

- **`artifact_blobs` is internal storage only** — NOT part of the generated entity pipeline. No `schemas/*.schema.json`, no Pydantic/Zod/TS DTO, no wire exposure of the model itself. It is reached only via `app/scan/persistence.py` (write) and `app/services/artifact_diff.py` + `app/routers/items.py` (read).
- **Capture is content-addressed + idempotent.** `persistence.py::_capture_snapshot` upserts with `pg_insert(...).on_conflict_do_nothing(index_elements=["sha256"])` — identical bytes never duplicate, re-scans are cheap.
- **Text-only, per-file cap.** Binaries (null-byte heuristic) and files over the per-file cap (`_SNAPSHOT_MAX_PER_FILE_BYTES`, 5 MiB) are recorded as `{path: null}` — present but not stored.
- **Verbatim, not redacted.** Bytes are stored as-is (public GitHub content at the scanned ref). This is the one locked exception to `.claude/rules/security.md` § Secrets Management #5; the scan *trace* stays no-raw-payload. See § Scan-trace transparency there.

### Retention + deletion

- Stored snapshots are the **"stored public artifact snapshots"** retention tier (`security.md` § Vendor-data isolation): public + indefinite + immutable per scan.
- **Deletion is via the vendor-appeals workflow only** (`vendor-appeals.md`) — never an inline user delete. An appeal clears the affected scan's `file_hashes` references; the blob rows themselves are **swept later** (a blob unreferenced by any scan's `file_hashes` is eligible for a background sweep), NOT hard-deleted inline (a blob may be shared by other scans/items via dedup).

## Upload + visibility (`upload_files`, migration 0008)

I-3.5 adds direct artifact upload + private (unlisted) scans. Uploads are a second front-end producing the same per-capability file index; visibility (`public` | `unlisted`) and `source_kind` (`github` | `upload`) are orthogonal columns on `scan_runs` + `catalog_items`. An upload may be **one file, one `.zip`, or N loose files** — all three resolve to the same combined `files_index` the engine scans like a repo, so the schema is unchanged. For a multi-file batch `scan_runs.original_filename` is the display label `"{n} files"` (the durable `content_hash_sha256` is computed from `files_index`, so the public-upload idempotency cache is unaffected by the label).

**Multi-file fan-out (per-file tabs report) needs NO migration.** A **flat** multi-file upload (top-level files, no subdirectories) fans into **one capability per file** (`discover_capabilities(source_kind="upload")`, runtime-only) — even when one file is a recognized anchor like `SKILL.md`; a structured `.zip` with subdirectories keeps normal directory-based discovery. It persists as N `scans` + N `catalog_items` under one `scan_runs` row, exactly the existing fan-out `persist_completed_scan_run` already handles. The per-file source viewer + `.zip` are read from the pre-existing `scans.manifest_*` + `scans.file_hashes` columns (`_pick_manifest` gains a single-loose-file fallback); the report DTO carries them per-`CapabilityRow`. No new column, no head-revision bump (still `0008_add_upload_and_visibility`).

### Schema additions

| Piece | Shape | Role |
|---|---|---|
| `scan_runs.visibility` | `VARCHAR(20)` NOT NULL DEFAULT `'public'` (chk IN `public`,`unlisted`) | Run-level visibility. Unlisted runs skip the public catalog, mint a `share_token`, and expire. |
| `scan_runs.source_kind` | `VARCHAR(20)` NOT NULL DEFAULT `'github'` (chk IN `github`,`upload`) | Where the bytes came from. |
| `scan_runs.share_token` | `VARCHAR(64)` NULL UNIQUE | Unguessable token; the `/scans/r/<token>` permalink key for unlisted runs. |
| `scan_runs.expires_at` | `TIMESTAMPTZ` NULL | Unlisted-only TTL (90 days). Partial index `idx_scan_runs_expires_at WHERE visibility='unlisted'`. |
| `scan_runs.original_filename` | `VARCHAR(255)` NULL | The uploaded file's display name (uploads only). |
| `scan_runs.content_hash_sha256` | `VARCHAR(64)` NULL | The durable `artifactSha256` source — sha256 of the sorted `{path → sha256}` map. Drives the public-upload slug `arthash8`. |
| `scans.github_url` / `scans.ref_sha` | **both relaxed to NULLABLE** | Uploads set both NULL — no synthetic sentinel. `scans.catalog_item_id` stays NOT NULL. |
| `catalog_items.visibility` / `source_kind` | same checks + defaults as on `scan_runs` | Mirrors run visibility onto the catalog row. Indexed `idx_catalog_items_visibility`. |
| `catalog_items.owner_run_id` | `UUID` NULL FK → `scan_runs(id)` `ON DELETE CASCADE` | The **shadow-row marker** — NULL on canonical (public) rows, set on per-run unlisted shadow rows. Partial index `idx_catalog_items_owner_run_id WHERE owner_run_id IS NOT NULL`. |
| `catalog_items.github_org` / `github_repo` / `default_branch` | **relaxed to NULLABLE** | Uploads have no repo coordinates (`github_url` was already nullable). |
| `rate_limits.bucket` chk | `chk_rate_limits_bucket` recreated | Adds `private_lookup` (now: `scan_submit`, `scan_read`, `item_read`, `item_list`, `artifact_download`, `private_lookup`). |
| `upload_files` (NEW) | `id` UUID PK; `scan_run_id` UUID NOT NULL FK → `scan_runs(id)` `ON DELETE CASCADE`; `path` VARCHAR(1024); `content` BYTEA NULL; `byte_size` INTEGER; `is_binary` BOOLEAN DEFAULT false; `created_at`. Index `idx_upload_files_scan_run_id`. | Per-run upload byte store for unlisted uploads. |

### `upload_files` contract

- **Internal storage only** — NOT part of the generated entity pipeline (no `schemas/*.schema.json`, no Pydantic/Zod/TS DTO, no wire exposure). Mirrors `artifact_blobs`. Hand-written model `app/models/upload_file.py`, registered in `app/models/__init__.py`.
- **Per-run, NO dedup.** Unlike `artifact_blobs` (content-addressed, shared), `upload_files` rows are scoped to one `scan_run_id` — per-run isolation avoids dedup-induced privacy coupling between unlisted runs.
- **`content` NULL = binary/oversize sentinel** (same heuristic as snapshots: null-byte detection + per-file cap).

### Visibility-split storage rule (D-UP-12)

Where scanned bytes land depends on `source_kind × visibility`:

| Source × visibility | Store | Dedup | Retention |
|---|---|---|---|
| `github` (any visibility) + `upload` / `public` | `artifact_blobs` (reuse `_capture_snapshot`) | yes (content-addressed) | indefinite |
| `upload` / `unlisted` | `upload_files` (per `scan_run_id`) | no | 90-day `expires_at` |

The read resolver is `app/services/artifact_bytes.py::resolve_snapshot(session, scan)` + `resolve(session, scan, path, sha)` — `artifact_blobs` first by sha, else `upload_files` by `scan_run_id + path`. `artifact_diff.load_snapshot` now delegates to `resolve_snapshot`.

### Unlisted catalog identity — per-run shadow rows (Option A)

- Public scans use `ensure_capability_item` (canonical, `owner_run_id=NULL`); public uploads use `ensure_upload_capability_item` (canonical, `source_kind='upload'`, `sources=[{registryId:'upload',...}]`).
- Unlisted runs (github OR upload) use `create_unlisted_shadow_item` — a fresh row with `owner_run_id=run.id`, `visibility='unlisted'`. Shadow slugs are never served from the public catalog.

### Deletion contract — `delete_run_cascade`

The `scans → scan_runs` FK **stays `ON DELETE SET NULL`** (not altered by 0008). Run deletion goes through the explicit ordered routine `app/scan/persistence.py::delete_run_cascade(session, run_id, *, allow_public=False)`, which deletes in order: **findings** (by scan_id in the run's scans) → **scan_events** → **scans** → **shadow `catalog_items`** (`owner_run_id` only) → **upload_files** → **scan_runs**. It **never touches `artifact_blobs`** (shared/deduped — swept separately). Token-delete + the expiry sweep call it with `allow_public=False` (refuse public runs); only the operator runbook passes `allow_public=True`.

### Expiry sweep

`app/core/sweeps.py::run_sweep_loop` — an in-process asyncio loop every `SWEEP_INTERVAL_SECONDS` (default 3600) under a **NEW** advisory lock `0x5AFE5C12` (distinct from the migration lock `0x5AFE5C11`). Started from the FastAPI lifespan in `app/main.py` AFTER `run_startup` + pool init, only when `startup_state.is_healthy`, and cancelled on shutdown. `sweep_unlisted(session)` deletes `scan_runs WHERE visibility='unlisted' AND expires_at < now()` via `delete_run_cascade`. `sweep_ingestion_runs(session)` (same tick, same `0x5AFE5C12` lock) deletes `ingestion_runs WHERE started_at < now() - interval '90 days'`. Coexists with the existing unreferenced-`artifact_blobs` sweep.

## Ingestion runs (`ingestion_runs`, migration 0013)

The eagle-eye observability table — **one row per ingestion cycle attempt**, written by `app/ingestion/tasks.py` at the cycle chokepoint in **independent sessions** (2 commits: a `running` row on start via `record_run_started`, a `succeeded`/`failed` update on end via `record_run_finished`), so a cycle whose own transaction rolls back still leaves a durable failure record.

| Piece | Shape | Role |
|---|---|---|
| `ingestion_runs` | `id` UUID PK; `source`; `trigger` (chk `scheduled`/`manual`/`force`); `status` (chk `running`/`succeeded`/`failed`); `started_at`/`ended_at`/`duration_ms`; `items_seen`/`items_added`/`items_updated`/`http_304_count`/`http_5xx_count`; `attempt`; `error_class`/`error_message` (≤2048 chars); `created_at` | Run history + rolling failure-window source for `GET /admin/sources` + `…/{source}/runs`. |

- **Internal storage only** — NOT part of the generated entity pipeline (no `schemas/*.schema.json`, no Pydantic/Zod/TS DTO, no wire model). Hand-written `app/models/ingestion_run.py`, registered in `app/models/__init__.py`. The admin endpoints serialize it via hand-built dicts (the `data`-envelope style), never a generated response_model.
- **`error_message` is bounded exception text only** — never raw artifact payload (the scan-trace no-raw-payload invariant, `security.md`).
- **Run-level metrics come from here; cursor-level health stays on `crawler_cursors`** (`consecutive_failure_count` + `last_successful_cycle_at`). The pure verdict logic is `app/ingestion/framework/health.py`. The `trigger` is threaded from the call site: periodic → `scheduled`, admin force-cycle → `force`, `run_one_cycle` → `manual`.
- **Retention: 90 days**, swept by `sweep_ingestion_runs` (§ Expiry sweep, lock `0x5AFE5C12`).

## Install events (`install_events`, migration 0015)

The opt-in install-telemetry store (I-05, D-05-31) — **one row per opt-in install reported by the `saferskills` CLI** (`POST /api/v1/installs`). Replaces the `items.py::_mock_install_activity` placeholder with a real GROUP-BY aggregate (this_week/this_month/all_time + agent distribution).

| Piece | Shape | Role |
|---|---|---|
| `install_events` | `id` UUID PK; `catalog_item_id` UUID FK → `catalog_items(id)` `ON DELETE CASCADE`; `agent` (native enum — the 8-agent set); `kind` (native enum — reuses the `0009` `kind` type); `cli_version` VARCHAR(32) NULL; `redacted_ip` VARCHAR(64) NULL; `created_at`. Index `idx_install_events_item_created (catalog_item_id, created_at DESC)`. | Real `install_activity` counts on the item-detail surface. |

- **Internal storage only** — NOT part of the generated entity pipeline (no `schemas/*.schema.json`, no Pydantic/Zod/TS DTO, no wire model). Hand-written `app/models/install_event.py`, registered in `app/models/__init__.py`. The endpoint DTOs (`InstallReportRequest`, `AgentShare`) are hand-written wrappers, not generated entity shapes.
- **Native `agent` enum is NEW in 0015** (the 8 canonical ids); the `kind` enum is reused from `0009`. The closed `agent` value set is shared by the migration, `app/models/install_event.py::AGENT_VALUES`, and `app/services/agent_compat.py::AgentName` — change all three + a migration for a new agent.
- **`redacted_ip` is `/24`-(v4) or `/48`-(v6) at write time** (`app/routers/installs.py` via `access_log_middleware.redact_ip`) — a raw IP is never stored. Closed-enum agent + kind only; no slug-in-clear, no PII (`privacy.md` + `security.md` § Vendor-data isolation).
- **Retention: retained** (redacted, no PII) so the `all_time` count survives — distinct from `access_log`'s 30-day sweep. Opt-in only (CLI first-run consent).

## When to update this rule

| Change | Updates here |
|---|---|
| New migration / head revision | "Migrations" — bump the current-head note |
| New stored-content table or column | "Stored artifact snapshots" table + `security.md` retention tier |
| Snapshot capture cap / heuristic change | "Stored artifact snapshots" § Contract + `app/scan/persistence.py` |
| Blob-sweep job lands | "Retention + deletion" — replace "swept later" with the job + cadence |
| New visibility / source_kind value or upload store change | "Upload + visibility" — table + storage-split rule + `security.md` retention tier |
| Sweep cadence / lock change | "Expiry sweep" — `app/core/sweeps.py` + `SWEEP_INTERVAL_SECONDS` + `environment-config.md` |
| `ingestion_runs` column / retention / trigger-enum change | "Ingestion runs" + `app/models/ingestion_run.py` + `app/ingestion/tasks.py` + migration |
| `delete_run_cascade` order / scope change | "Deletion contract" — re-verify `artifact_blobs` is never touched inline |
| `install_events` column / enum / retention change | "Install events" + `app/models/install_event.py` + `app/routers/installs.py` + migration 0015 + `privacy.md` + `security.md` |
| New internal (hand-written) model added | "Models are codegen-driven" — extend the thirteen-store list + `app/models/__init__.py` docstring; confirm it has no wire DTO (else it must be schema-driven/generated) |
| New always-on store (would violate single-store) | `tech-stack.md` first — then here |
