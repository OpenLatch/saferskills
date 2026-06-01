# Database

> **Paths**: `services/api/migrations/**`, `services/api/app/models/**`, `services/api/app/db/**`, `services/api/alembic.ini`

PostgreSQL 17, single store (no Redis — in-process LRU only, per `tech-stack.md`). SQLAlchemy 2 async (`AsyncSession` everywhere), Alembic for migrations. This rule lands with the first real content-storage subsystem: `artifact_blobs` (Phase B).

## Migrations

- **Auto-applied in-process on every API boot, every environment.** `app/core/startup.py::run_startup` runs `alembic upgrade head` under a session-level `pg_advisory_lock` (key `0x5AFE5C11`) — race-safe across concurrent Machines. No Fly `release_command`, no manual migrate step. See `.claude/rules/ci-cd.md` § Deployment.
- **One revision per schema change**, named `YYYY_MM_DD_NNNN_<slug>.py`, `down_revision` chained to the prior head. Current head: `0006_add_artifact_blobs` (down-rev `0005_add_scan_manifest`).
- **Every migration is reversible** — `downgrade()` drops what `upgrade()` adds. Current head: `0007_per_capability_scans` (down-rev `0006_add_artifact_blobs`).
- Naming follows `.claude/rules/naming-conventions.md` § Database (plural snake_case tables, `idx_`/`uq_`/`chk_` constraints, `<singular>_id` FKs).
- Production models are hand-written under `app/models/` and registered in `app/models/__init__.py` (the 4-column `generated/` stubs don't match the real schema yet). New model = new import there so `Base.metadata` sees it.

## Per-capability scans (`scan_runs`)

One repo scan discovers + scores N capabilities (a Skill, an MCP server, hooks, …) and fans out to N `scans` rows grouped under one `scan_runs` row. This overturns the original *"one catalog_item per (github_org, github_repo)"* decision — **one catalog_item = one capability**, and several capabilities can share one repo URL.

| Piece | Shape | Role |
|---|---|---|
| `scan_runs` | `id` PK; `idempotency_key` UNIQUE; `github_url`/`ref_sha`; `repo_aggregate_score` (0–100 chk) + `repo_tier` (chk); `kind_tally` JSONB; `capability_count`; `rubric_version`/`engine_version`/`source` (chk)/`latency_ms`/`file_count`; `status` (chk); timestamps | The repo scan. `repo_aggregate_score` = rounded mean of its capability scores. `/scans/runs/<run_id>` is the repo report. |
| `scans.scan_run_id` | nullable FK → `scan_runs` (`SET NULL`) | Links a per-capability scan to its run. Backfilled 1:1 for legacy/seed scans. |
| `scans.component_path` | String(1024) nullable | Relative path of the scanned capability subtree (`null`/`""` = whole-repo). |
| `scan_events.scan_run_id` | nullable FK → `scan_runs` (`CASCADE`) | SSE progress re-keys onto the run (channel `scan_progress_<run_id>`); `scan_events.scan_id` is now nullable. |

- **`UNIQUE(catalog_items.github_url)` is dropped** (replaced with non-unique `idx_catalog_items_github_url`) — shared-repo capabilities need it. The slug UNIQUE stays; per-capability slug is `<org>--<repo>--<kind>-<name>[-<hash6>]` (see `naming-conventions.md` § slug grammar).
- **Discovery → fan-out** lives in `app/scan/discovery.py` (pure) + `app/scan/engine.py::run_repo_scan`; persistence in `app/scan/persistence.py::persist_completed_scan_run`. Snapshots/manifests are **per-capability subtree**.
- **Backfill (migration 0007):** one `scan_runs` row per existing `scans` row (each a 1-capability run, reusing the scan's idempotency_key). Removed capabilities on a rescan are **not deleted** (archived-public policy).

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

## When to update this rule

| Change | Updates here |
|---|---|
| New migration / head revision | "Migrations" — bump the current-head note |
| New stored-content table or column | "Stored artifact snapshots" table + `security.md` retention tier |
| Snapshot capture cap / heuristic change | "Stored artifact snapshots" § Contract + `app/scan/persistence.py` |
| Blob-sweep job lands | "Retention + deletion" — replace "swept later" with the job + cadence |
| New always-on store (would violate single-store) | `tech-stack.md` first — then here |
