# CI/CD Requirements

All checks must pass before merge. Every third-party action is **SHA-pinned** (never floating tags); the first step of every workflow is `step-security/harden-runner`; every workflow declares `permissions: contents: read` at the top and elevates per-job only when needed.

## Pipeline lanes (14 + `all-checks` aggregation)

`pr-checks.yml` runs 14 lanes plus the aggregator (the 13 W1 lanes + `lighthouse-a11y`, added in I-03 Phase C). Tools are SHA-pinned in `.github/actions/` reusable composites.

| # | Lane | What it does |
|---|---|---|
| 1 | `validate` | JSON Schema validation (ajv-cli), schema-to-code generation drift check (regenerates Pydantic + SQLAlchemy + `openapi.json` + TS DTOs + Zod; fails if `git diff --exit-code` is non-empty), no-CDN-fonts grep, placeholder-taxonomy grep, and **CSS token discipline** (`node scripts/check-css.cjs` — no stale `var(--x,#hex)` fallbacks, no undefined tokens, no raw hex in shell page CSS; see `design-system.md` § CSS token discipline) |
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
| 14 | `lighthouse-a11y` | `@lhci/cli` (Lighthouse, **observe-mode `warn`** on the no-seed public pages — reports uploaded, not yet hard-gating; promote categories to `error` once perf is baselined in this CI env) + `@axe-core/playwright` WCAG 2 A/AA smoke as the **hard** a11y gate. Runs on PRs touching `webapp/**` or `ui/**` (gated on `detect-changes.outputs.frontend`). Brings up postgres+api from the smoke compose, builds + serves the webapp Node SSR on :5173 (`--no-sandbox` Chrome). Seeded pages (item-detail / scan-report) are Lighthoused in the staging e2e. (I-03 Phase C) |
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

## Deployment (Track D — staging live, prod gated until MVP)

Staging deploys on every push to `main` via `deploy.yml` (`deploy-staging-api` / `deploy-staging-webapp` → `saferskills-{api,webapp}-staging.fly.dev`) and is followed by `e2e-staging` Playwright smoke. Production deploys are **gated off until SaferSkills reaches MVP state**: the prod jobs only run when the repo variable `ENABLE_PRODUCTION_DEPLOYS` equals `"true"` (currently unset). In parallel, the prod Fly apps `saferskills-api` / `saferskills-webapp` are kept in `suspended` state with zero machines — flipping the variable alone is not sufficient, a maintainer must also `flyctl apps resume` before the first prod deploy lands. When that happens:

- **Unified pipeline** (`deploy.yml`): push to `main` → build ALL images → deploy staging (path-filtered) → smoke → deploy production (canary, atomic image+secrets, 5-min soak, auto-rollback on failure).
- **Production canary**: `fly.production.toml` uses `strategy = "canary"` — boots one Machine first, health-checks it, auto-aborts on failure.
- **Production deploys are always-all-services**: every approved prod deploy ships both services (api + webapp) at the current `main` SHA, regardless of path filter. Prevents stale-image drift.
- **Atomic image + secrets roll**: `flyctl secrets set --stage ...` + `flyctl deploy --image registry.fly.io/saferskills-<svc>:main-<sha>` in one job per service. Never split `sync-secrets-*` from `deploy-*`. The API deploy jobs stage `TURNSTILE_SECRET_KEY` (from the GH Actions secret of the same name, skipped when unset) before `flyctl deploy` so the secret + image land in one release. With `ENV=production` the API startup guard **requires** that secret — set the GH secret before the first prod deploy.
- **Build-time public config (`PUBLIC_*`) is a build-arg, not a Fly secret**: `PUBLIC_*` values are inlined into the Astro bundle at `pnpm build` (inside the webapp image build), so they must be passed as Docker `--build-arg`s in the `build-and-push` job — `GIT_SHA` and `PUBLIC_TURNSTILE_SITE_KEY` (the latter from the GH Actions secret `PUBLIC_TURNSTILE_SITE_KEY`, declared `ARG` in `webapp/Dockerfile`). One image is shared by staging + prod, so a `PUBLIC_*` value is identical across environments; a build-arg cannot be changed per-env without a rebuild. Setting such a value as a Fly runtime secret has no effect (the bundle is already built).
- **Force-start stopped machines after every prod `flyctl deploy`**: `flyctl machine list --app saferskills-<svc> --json | jq -r '.[].id' | while read mid; do flyctl machine start --app saferskills-<svc> "$mid" || true; done`. No-op on running machines; mandatory on a fleet that may be stopped (Flycast / scale-to-zero, internal 6PN bypasses Fly's auto-start edge).
- **Images (dual-registry push)**: every CI build pushes the same image bytes to BOTH `ghcr.io/openlatch/saferskills-<svc>` (canonical archive with cosign keyless signatures + SBOMs + SLSA L3 provenance via `slsa-framework/slsa-github-generator`) AND `registry.fly.io/saferskills-<svc>` (Fly's private registry). Deploys use the Fly ref because Fly cannot auth to private third-party registries. Digests are identical in both; cosign signatures on the ghcr ref transfer to the Fly copy.
- **Migrations**: the API runs `alembic upgrade head` **in-process on every Machine boot, in every environment** (`app/core/startup.py`, invoked from the FastAPI lifespan). There is **no** Fly `release_command` and **no** `alembic` step in `deploy.yml` — boot handles it. Concurrent Machines on a multi-machine deploy are race-safe via a session-level `pg_advisory_lock` (key `0x5AFE5C11`): the first Machine runs the DDL, later Machines block on the lock then see `head` and no-op. On failure the API enters degraded mode (503 on all routes but `/api/v1/health`) rather than crash-looping — see `app/core/middleware.py::StartupGuardMiddleware`.
- **Rollback**: `rollback-production.yml` for fast manual rollback to a known-good image tag.
- **CLI**: `flyctl` — never any other host CLI.
- **Secrets**: `fly secrets set --stage` on prod, never `fly secrets set` without `--stage`.
- **Config**: `fly.staging.toml` / `fly.production.toml` per service directory.

## Dependency-bump policy

- **Dependabot** drives every ecosystem (npm root + pip `services/api` + pip `tools/e2e` + docker + github-actions). Weekly Monday schedule, grouped PRs per ecosystem (`frontend-minor-patch`, `api-minor-patch`, etc.).
- Every dep on its current latest major or latest stable minor. Both minor/patch and major bumps are grouped per ecosystem (`frontend-major`, `api-major`, etc.) to keep the PR queue small — see `.github/dependabot.yml`. Major-group PRs land as a single combined bump with a migration note in the PR body.

## Pre-Commit Hooks

Installed via `pre-commit install` in repo root. Source of truth: `.pre-commit-config.yaml`.

**Security**
- `gitleaks` — block credential-shaped strings in staged files

**Python (Ruff)**
- `ruff-check --fix` — lint + autofix
- `ruff-format` — format

**TS / JS / JSON (Biome)**
- `biome-check` — lint + format in one pass

**JSON Schema validation (`check-jsonschema`)**
- `check-metaschema` — validate `schemas/*.json` against the JSON Schema metaschema
- `check-github-workflows` — validate `.github/workflows/*.yml`
- `check-compose-spec` — validate `docker-compose*.yml`
- `check-dependabot` — validate `.github/dependabot.yml`

**Repo hygiene (`pre-commit-hooks`)**
- `trailing-whitespace`, `end-of-file-fixer`
- `check-yaml` (with `--unsafe` for custom tags), `check-json`
- `check-added-large-files` (>1000 KB blocked)
- `check-merge-conflict`, `check-case-conflict`

**Commit message (commit-msg stage)**
- `conventional-pre-commit` — enforce Conventional Commits format (allowed types: feat, fix, docs, style, refactor, perf, test, build, ci, chore, revert)

## When to update this rule

| Change | Updates here |
|---|---|
| New lane added or removed | "Pipeline lanes" table |
| New always-on workflow | "Always-on workflows" table |
| New service shipped (deploy ships W2-W3) | "Deployment" — re-verify always-all-services + force-start loop |
| New dependency-bump source | "Dependency-bump policy" |
| New pre-commit hook | "Pre-Commit Hooks" |
