# saferskills-data-seed

Multi-purpose dev tool for SaferSkills. One CLI, five domains:

- **`catalog`** — publish ~50 fixture items via `POST /api/v1/scans`.
- **`scans`** — list / run individual scans (useful for re-running after rubric changes).
- **`vendors`** — issue verification tokens, redeem them against test repos, seed vendor responses.
- **`doctor`** — preflight (API reachable, OpenAPI schema matches, fixture corpus validates).
- **`purge`** — reset the database to a clean state. **Local / staging only.** Hard rails: allowlist + `--apply` + `--yes`/env confirm.

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

## Safety rails

The `purge run --apply` path **refuses** unless ALL of the following hold:

1. `--api-url` matches the allowlist: `http://localhost:8000`, `http://api:8000`, `https://staging.saferskills.ai`. Production base URLs are intentionally absent — adding one requires editing `saferskills_data_seed/domains/purge/app.py` and the matching review.
2. Either `--yes` is passed OR the env `SAFERSKILLS_DATA_SEED_CONFIRM=yes-i-mean-it` is set.
3. A 3-second `time.sleep` gives the operator a chance to Ctrl+C after the target + counts are printed.

Every purge request sends `User-Agent: saferskills-data-seed/0.1.0` so backend logs can flag it.

## Phase-readiness

| Domain | A1 ships | Notes |
|---|---|---|
| `catalog list / describe` | ✓ | Reads the bundled `catalog.yaml` (8 entries in A1; full 50 entries in a follow-up). |
| `catalog publish` | ✓ scaffold | The CLI POSTs to `/api/v1/scans` — that endpoint lands with Phase B. Running A1 against W1 backend returns 404 (caught + reported). |
| `scans list / run` | ✓ scaffold | Same — endpoint lands with Phase B. |
| `vendors verify-issue / verify-redeem / seed` | ✓ scaffold | Vendor right-of-reply ships with Phase C. |
| `doctor` | ✓ | Checks API reachability + corpus parse. Real-now. |
| `purge` | ✓ | Real safety rails; backend admin DELETE endpoints land with Phase B. |
