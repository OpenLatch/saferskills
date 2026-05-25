# CI/CD Requirements

All checks must pass before merge. Every third-party action is **SHA-pinned** (never floating tags); the first step of every workflow is `step-security/harden-runner`; every workflow declares `permissions: contents: read` at the top and elevates per-job only when needed.

## Pipeline lanes (W1: 14 + `all-checks` aggregation)

`pr-checks.yml` runs 14 lanes plus the aggregator. Tools are SHA-pinned in `.github/actions/` reusable composites.

| # | Lane | What it does |
|---|---|---|
| 1 | `validate` | JSON Schema validation (ajv-cli), schema-to-code generation drift check (regenerates Pydantic + SQLAlchemy + `openapi.json` + TS DTOs + Zod; fails if `git diff --exit-code` is non-empty) |
| 2 | `lint-fe` | Biome (`pnpm biome check .`) — TS/JS/JSON |
| 3 | `lint-be` | Ruff (`uv run ruff check . && uv run ruff format --check .`) |
| 4 | `typecheck-fe` | `pnpm astro check` + `pnpm tsc --noEmit` |
| 5 | `typecheck-be` | `uv run pyright` |
| 6 | `test-fe` | Vitest (≥70% line coverage) |
| 7 | `test-be` | pytest (≥70% line coverage) |
| 8 | `ladle-build` | `pnpm ladle:build` — catches broken stories, missing imports, render errors. Runs on PRs touching `ui/` or `webapp/src/components/` |
| 9 | `docker-build` | Parallel matrix (api + webapp) with scoped GHA cache |
| 10 | `docker-smoke` | `docker compose -f ci/docker-compose.smoke.yml up` — postgres + api + webapp boot + `/healthz` 200 |
| 11 | `trivy-scan` | Trivy vulnerability scanner (CRITICAL/HIGH) with SARIF upload to GitHub Security tab |
| 12 | `dep-scan` | `pip-audit` (`uv pip compile`) + `pnpm audit --audit-level=high` |
| 13 | `pr-title-lint` | Conventional Commits format check |
| 14 | `dco-check` | Every commit signed-off (`Signed-off-by:` trailer) per DCO |
| – | `all-checks` | Aggregation job — gates merge; depends on all 14 |

Both smoke + build lanes gate positively on a `dorny/paths-filter` `changes` matcher (`backend`/`frontend`/`schemas`/`ci`); they skip only when the PR is **pure docs**. Mixed code+docs PRs run the full pipeline.

## Always-on workflows (W1)

| File | Cadence | Purpose |
|---|---|---|
| `scorecard.yml` | Weekly + on push to `main` | OpenSSF Scorecard — publishes to `securityscorecards.dev` and SARIF |
| `release-please.yml` | On push to `main` | **Dormant at W1** (no `v1.0.0` release yet); flips on first tagged release |
| CodeQL (UI default-setup) | On PR + nightly | Static analysis for Python + TypeScript |

## Post-Implementation Verification

After completing a feature, fixing a bug, or refactoring — and before opening a PR — run `/verify-build`. It auto-detects changed layers and runs the appropriate quality gates (build, typecheck, lint, tests). A session that leaves broken checks is a failed session.

## Deployment (when Track D ships W2-W3)

W1 is unhosted (preview deploys via Fly.io launch later in Track D). When deploy ships:

- **Unified pipeline** (`deploy.yml`): push to `main` → build ALL images → deploy staging (path-filtered) → smoke → deploy production (canary, atomic image+secrets, 5-min soak, auto-rollback on failure).
- **Production canary**: `fly.production.toml` uses `strategy = "canary"` — boots one Machine first, health-checks it, auto-aborts on failure.
- **Production deploys are always-all-services**: every approved prod deploy ships both services (api + webapp) at the current `main` SHA, regardless of path filter. Prevents stale-image drift.
- **Atomic image + secrets roll**: `flyctl secrets set --stage ...` + `flyctl deploy --image registry.fly.io/saferskills-<svc>:main-<sha>` in one job per service. Never split `sync-secrets-*` from `deploy-*`.
- **Force-start stopped machines after every prod `flyctl deploy`**: `flyctl machine list --app saferskills-<svc> --json | jq -r '.[].id' | while read mid; do flyctl machine start --app saferskills-<svc> "$mid" || true; done`. No-op on running machines; mandatory on a fleet that may be stopped (Flycast / scale-to-zero, internal 6PN bypasses Fly's auto-start edge).
- **Images (dual-registry push)**: every CI build pushes the same image bytes to BOTH `ghcr.io/openlatch/saferskills-<svc>` (canonical archive with cosign keyless signatures + SBOMs + SLSA L3 provenance via `slsa-framework/slsa-github-generator`) AND `registry.fly.io/saferskills-<svc>` (Fly's private registry). Deploys use the Fly ref because Fly cannot auth to private third-party registries. Digests are identical in both; cosign signatures on the ghcr ref transfer to the Fly copy.
- **Migrations**: API uses `release_command` in `fly.toml` — runs `alembic upgrade head` once before any Machine starts. Startup code skips migrations in production.
- **Rollback**: `rollback-production.yml` for fast manual rollback to a known-good image tag.
- **CLI**: `flyctl` — never any other host CLI.
- **Secrets**: `fly secrets set --stage` on prod, never `fly secrets set` without `--stage`.
- **Config**: `fly.staging.toml` / `fly.production.toml` per service directory.

## Dependency-bump policy

- **Dependabot** drives every ecosystem (npm root + pip `services/api` + pip `tools/e2e` + docker + github-actions). Weekly Monday schedule, grouped PRs per ecosystem (`frontend-minor-patch`, `api-minor-patch`, etc.).
- Every dep on its current latest major or latest stable minor; major bumps reviewed individually.

## Pre-Commit Hooks

Installed via `pre-commit install` in repo root:
- `ruff format` + `ruff check --fix` (Python)
- `biome check --write` (TS/JS/JSON)
- `ajv validate` (JSON Schema validation)
- `detect-secrets-hook` (prevent credential commits)
- `dco-signoff` (verify `Signed-off-by:` trailer)

## When to update this rule

| Change | Updates here |
|---|---|
| New lane added or removed | "Pipeline lanes" table |
| New always-on workflow | "Always-on workflows" table |
| New service shipped (deploy ships W2-W3) | "Deployment" — re-verify always-all-services + force-start loop |
| New dependency-bump source | "Dependency-bump policy" |
| New pre-commit hook | "Pre-Commit Hooks" |
