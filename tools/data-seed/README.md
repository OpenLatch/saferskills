<div align="center">

<a href="../../README.md">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="../../webapp/public/logos/saferskills-dark-wordmark.svg">
    <img alt="SaferSkills" src="../../webapp/public/logos/saferskills-light-wordmark.svg" height="38">
  </picture>
</a>

<h3>Data-seed CLI</h3>
<p>Dev tool to publish fixtures, run scans, and reset a local database.</p>

</div>

## What it is

A multi-purpose dev tool for SaferSkills. One CLI, five domains:

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

SaferSkills has **no admin bulk-delete HTTP endpoint** by design (deletion is vendor-appeals / operator-runbook only — see [`security.md`](../../.claude/rules/security.md)), so `purge` is a **direct DB operation**, not an API call. It connects with psycopg and runs one `TRUNCATE … RESTART IDENTITY CASCADE` over **every** public table *except* `alembic_version` (so the schema stays at head). The table set is **discovered at runtime** from `pg_tables` — there is no hardcoded list to drift against the schema, so new tables (`scan_runs`, `scan_events`, `upload_files`, `artifact_blobs`, `item_sources`, …) are covered automatically and no FK orphans are left behind.

```bash
# Inspect target + per-table row counts (read-only)
uv run saferskills-data-seed purge describe

# Non-default DSN (else DATABASE_URL env, else the dev default)
uv run saferskills-data-seed purge run --apply --yes \
  --database-url postgresql://postgres:dev@localhost:5432/saferskills_dev
```

The `purge run --apply` path **refuses** unless ALL of the following hold:

1. The DB host resolves to loopback (`localhost`, `127.0.0.1`, `::1`). Remote hosts (staging/prod are Fly-internal and unreachable from a laptop anyway) exit 2 — widening this requires editing `HOST_ALLOWLIST` in `saferskills_data_seed/domains/purge/app.py` and the matching review.
2. Either `--yes` is passed OR the env `SAFERSKILLS_DATA_SEED_CONFIRM=yes-i-mean-it` is set.
3. A 3-second `time.sleep` gives the operator a chance to Ctrl+C after the target is printed.

A SQLAlchemy-style `postgresql+asyncpg://…` DSN (or a legacy `postgres://…`) is accepted — the `+asyncpg` driver suffix is stripped automatically so the same `DATABASE_URL` the API uses works here unchanged.

## See also

- [`tools/data-seed/CLAUDE.md`](./CLAUDE.md) — architecture + hard rules (loopback-only purge, paced publish, no `services/api/` imports)
- [`.claude/rules/security.md`](../../.claude/rules/security.md) — why there is no bulk-delete endpoint

---

<sub>Part of **[SaferSkills](../../README.md)** — every AI capability, independently scanned. · An [OpenLatch](https://openlatch.ai) project · [saferskills.ai](https://saferskills.ai)</sub>
