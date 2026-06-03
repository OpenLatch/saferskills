# saferskills-data-seed

Multi-purpose dev tool for SaferSkills. One CLI, five domains:

- **`catalog`** — publish ~50 fixture items via `POST /api/v1/scans`.
- **`scans`** — list / run individual scans (useful for re-running after rubric changes).
- **`vendors`** — issue verification tokens, redeem them against test repos, seed vendor responses.
- **`doctor`** — preflight (API reachable, fixture corpus validates).
- **`purge`** — reset the database to a clean, schema-at-head state via a direct `TRUNCATE`. **Loopback DB only.** Hard rails: host allowlist + `--apply` + `--yes`/env confirm.

## Setup

```bash
cd tools/data-seed
uv sync
```

## Quick start

```bash
# Preflight
uv run saferskills-data-seed doctor

# Publish the bundled fixture catalog
uv run saferskills-data-seed catalog publish --api-url http://localhost:8000

# Trigger an individual scan
uv run saferskills-data-seed scans run https://github.com/anthropics/skills

# Reset (default dry-run — needs --apply + --yes to actually delete)
uv run saferskills-data-seed purge run
uv run saferskills-data-seed purge run --apply --yes
```

## Purge — how it works

SaferSkills has **no admin bulk-delete HTTP endpoint** by design (deletion is
vendor-appeals / operator-runbook only — see `security.md`), so `purge` is a
**direct DB operation**, not an API call. It connects with psycopg and runs one
`TRUNCATE … RESTART IDENTITY CASCADE` over **every** public table *except*
`alembic_version` (so the schema stays at head). The table set is **discovered
at runtime** from `pg_tables` — there is no hardcoded list to drift against the
schema, so new tables (`scan_runs`, `scan_events`, `upload_files`,
`artifact_blobs`, `item_sources`, …) are covered automatically and no FK orphans
are left behind.

```bash
# Inspect target + per-table row counts (read-only)
uv run saferskills-data-seed purge describe

# Reset (default dry-run — needs --apply + --yes to actually delete)
uv run saferskills-data-seed purge run
uv run saferskills-data-seed purge run --apply --yes

# Non-default DSN (else DATABASE_URL env, else the dev default)
uv run saferskills-data-seed purge run --apply --yes \
  --database-url postgresql://postgres:dev@localhost:5432/saferskills_dev
```

The `purge run --apply` path **refuses** unless ALL of the following hold:

1. The DB host resolves to loopback (`localhost`, `127.0.0.1`, `::1`). Remote
   hosts (staging/prod are Fly-internal and unreachable from a laptop anyway)
   exit 2 — widening this requires editing `HOST_ALLOWLIST` in
   `saferskills_data_seed/domains/purge/app.py` and the matching review.
2. Either `--yes` is passed OR the env `SAFERSKILLS_DATA_SEED_CONFIRM=yes-i-mean-it` is set.
3. A 3-second `time.sleep` gives the operator a chance to Ctrl+C after the target is printed.

A SQLAlchemy-style `postgresql+asyncpg://…` DSN (or a legacy `postgres://…`) is
accepted — the `+asyncpg` driver suffix is stripped automatically so the same
`DATABASE_URL` the API uses works here unchanged.

## Phase-readiness

| Domain | A1 ships | Notes |
|---|---|---|
| `catalog list / describe` | ✓ | Reads the bundled `catalog.yaml` (8 entries in A1; full 50 entries in a follow-up). |
| `catalog publish` | ✓ scaffold | The CLI POSTs to `/api/v1/scans` — that endpoint lands with Phase B. Running A1 against W1 backend returns 404 (caught + reported). |
| `scans list / run` | ✓ scaffold | Same — endpoint lands with Phase B. |
| `vendors verify-issue / verify-redeem / seed` | ✓ scaffold | Vendor right-of-reply ships with Phase C. |
| `doctor` | ✓ | Checks API reachability + corpus parse. Real-now. |
| `purge` | ✓ | Real-now. Direct `TRUNCATE` of every table but `alembic_version` (runtime-discovered), loopback-gated. |
