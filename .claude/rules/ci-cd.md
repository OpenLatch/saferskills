# CI/CD Requirements

All checks must pass before merge. Every third-party action is **SHA-pinned** (never floating tags); the first step of every workflow is `step-security/harden-runner`; every workflow declares `permissions: contents: read` at the top and elevates per-job only when needed.

## Pipeline lanes (14 + 5 Rust CLI + `all-checks` aggregation)

`pr-checks.yml` runs 14 web/backend lanes + 5 Rust CLI lanes plus the aggregator (the 13 W1 lanes + `lighthouse-a11y` from I-03 Phase C + the 5 `cli-*` lanes from I-05). Tools are SHA-pinned in `.github/actions/` reusable composites.

| # | Lane | What it does |
|---|---|---|
| 1 | `validate` | JSON Schema validation (ajv-cli), schema-to-code generation drift check (regenerates the ingestion source-registry from `config/sources/*.yaml` + Pydantic + SQLAlchemy + `openapi.json` + TS DTOs + Zod; fails if `git diff --exit-code` is non-empty — this catches a provider YAML added without `pnpm run generate`), **outbound-host allowlist** (`node scripts/validate-outbound-allowlist.cjs` — self-derived from the YAML `hosts:` lists; every host an adapter `.py` fetches must be declared in some provider YAML), no-CDN-fonts grep, placeholder-taxonomy grep, and **CSS token discipline** (`node scripts/check-css.cjs` — no stale `var(--x,#hex)` fallbacks, no undefined tokens, no raw hex in shell page CSS; see `design-system.md` § CSS token discipline) |
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
| 15 | `cli-fmt` | `cargo fmt --manifest-path cli/Cargo.toml --all --check` (I-05) |
| 16 | `cli-clippy` | `cargo clippy --manifest-path cli/Cargo.toml --all-targets -- -D warnings` (I-05) |
| 17 | `cli-test` | `cargo llvm-cov` test + **≥70% line coverage** (`--fail-under-lines 70`) (I-05) |
| 18 | `cli-build` | `cargo build --release` + **<15 MB** size gate on the `saferskills` binary (I-05) |
| 19 | `cli-rustls` | `cargo tree -e normal` must contain no `openssl-sys` / `native-tls` — the rustls-only invariant (I-05) |
| – | `all-checks` | Aggregation job — gates merge; depends on all 19 |

The 5 `cli-*` lanes gate on a `dorny/paths-filter` `cli` matcher (`cli/**` + `.github/actions/setup-rust/**`) and use the `.github/actions/setup-rust` composite (toolchain + `cli/`-scoped cargo cache). Both smoke + build lanes gate positively on a `dorny/paths-filter` `changes` matcher (`backend`/`frontend`/`schemas`/`ci`); they skip only when the PR is **pure docs**. Mixed code+docs PRs run the full pipeline.

## Always-on workflows (W1)

| File | Cadence | Purpose |
|---|---|---|
| `scorecard.yml` | Weekly + on push to `main` | OpenSSF Scorecard — publishes to `securityscorecards.dev` and SARIF |
| `release-please.yml` | On push to `main` | **Dormant at W1** (no `v1.0.0` release yet); flips on first tagged release |
| CodeQL (UI default-setup) | On PR + nightly | Static analysis for Python + TypeScript |

## CLI release + publish (I-05)

The `saferskills` install CLI (a Rust crate in `cli/`) is the **only** `release-please`-managed package, so its tag is the bare `vX.Y.Z` (no component prefix; `include-component-in-tag: false`).

- **release-please**: `release-please-config.json` sets the `cli` package `release-type: "rust"` — it bumps `cli/Cargo.toml` + `cli/Cargo.lock` + `cli/CHANGELOG.md`. Merging the Release PR (via the `version-bump.yml` GitHub-App token) tags `vX.Y.Z`.
- **`publish-npm.yml`** (filename is load-bearing — the npm + crates.io Trusted-Publisher bindings verify it): on the tag it builds the **5-target matrix** (`aarch64`/`x86_64` Apple, `x86_64`/`aarch64` Linux via `cross`, `x86_64` Windows) with `--features telemetry-network`, size-gates each (<15 MB), cosign-keyless-signs + Syft-SBOMs them, uploads them to the GitHub Release, then: stamps + publishes the 5 scoped `@openlatch/saferskills-<platform>` packages **before** the unscoped `saferskills` main package (OIDC, no `NPM_TOKEN`), `cargo publish --manifest-path cli/Cargo.toml` (crates.io OIDC), and a 3-OS `verify-publish` smoke (`--version` / `--help` / `completion`). `workflow_dispatch` is build-only (never publishes).
- **Founder action (one-time, outbox/01)**: the 6 npm TP bindings + the crates.io TP binding → `publish-npm.yml`; `npm deprecate @openlatch/saferskills`. Provenance needs a public repo.

## Post-Implementation Verification

After completing a feature, fixing a bug, or refactoring — and before opening a PR — run `/verify-build`. It auto-detects changed layers and runs the appropriate quality gates (build, typecheck, lint, tests). A session that leaves broken checks is a failed session.

## Deployment (Track D — staging live, prod gated until MVP)

Staging deploys on every push to `main` via `deploy.yml` (`deploy-staging-api` / `deploy-staging-webapp` → `saferskills-{api,webapp}-staging.fly.dev`) and is followed by `e2e-staging` Playwright smoke. Production deploys are **gated off until SaferSkills reaches MVP state**: the prod jobs only run when the repo variable `ENABLE_PRODUCTION_DEPLOYS` equals `"true"` (currently unset). In parallel, the prod Fly apps `saferskills-api` / `saferskills-webapp` are kept in `suspended` state with zero machines — flipping the variable alone is not sufficient, a maintainer must also `flyctl apps resume` before the first prod deploy lands. When that happens:

- **Unified pipeline** (`deploy.yml`): push to `main` → build ALL images → deploy staging (path-filtered) → smoke → deploy production (canary, atomic image+secrets, 5-min soak, auto-rollback on failure).
- **Production canary**: `fly.production.toml` uses `strategy = "canary"` — boots one Machine first, health-checks it, auto-aborts on failure.
- **Production deploys are always-all-services**: every approved prod deploy ships both services (api + webapp) at the current `main` SHA, regardless of path filter. Prevents stale-image drift.
- **Atomic image + secrets roll**: `flyctl secrets set --stage ...` + `flyctl deploy --image registry.fly.io/saferskills-<svc>:main-<sha>` in one job per service. Never split `sync-secrets-*` from `deploy-*`. The API deploy jobs stage `TURNSTILE_SECRET_KEY` (from the GH Actions secret of the same name, skipped when unset) before `flyctl deploy` so the secret + image land in one release. With `ENV=production` the API startup guard **requires** that secret — set the GH secret before the first prod deploy. The deploy jobs also stage `SAFERSKILLS_PROXY_SHARED_SECRET` (from the GH Actions secret of the same name, skipped when unset) — on **both** the API app **and** the webapp app, since the value must be identical: it is how the API trusts the webapp `/api/*` proxy's forwarded visitor IP (the proxy sends it as `X-Proxy-Secret`). On the webapp it is a server-side **runtime** secret (the Node proxy reads it at request time), NOT a build-arg. The API deploy jobs additionally stage `SAFERSKILLS_ADMIN_KEY` (API apps only — the webapp does not use it; skipped when unset) — gating `/api/v1/admin/*`. Unlike the two above, it is an **environment-scoped** GH Actions secret (same name, distinct value per env: the staging job runs in `environment: staging`, the prod job in `environment: production`); without it the admin gate fails closed (403) since deploys always set `ENV` (the keyless exemption is local-dev only). The API deploy jobs also stage `SLACK_ALERTS_WEBHOOK_URL` (API apps only — the page-tier sink for I-04 ingestion alerts, `app/ingestion/framework/alerts.py`; skipped when unset). Unlike `SAFERSKILLS_ADMIN_KEY`, it is a **repo-level** GH Actions secret (same value both envs, like `TURNSTILE_SECRET_KEY` — the single Slack incoming-webhook is bound to one channel); unset → alerts degrade to Sentry/PostHog only (no Slack page), never a boot failure. **Set it via the GH Actions secret, not a manual `flyctl secrets set`** — CI is the source of truth so a redeploy never drops it. See `security.md` § Public-input handling #11 + Audit Trail + `environment-config.md`.
- **Build-time public config (`PUBLIC_*`) is a build-arg, not a Fly secret**: `PUBLIC_*` values are inlined into the Astro bundle at `pnpm build` (inside the webapp image build), so they must be passed as Docker `--build-arg`s in the `build-and-push` job — `GIT_SHA` and `PUBLIC_TURNSTILE_SITE_KEY` (the latter declared `ARG` in `webapp/Dockerfile`, valued from the GH Actions secret **`TURNSTILE_PUBLIC_SITE_KEY`** — the secret is `TURNSTILE_`-grouped, but the build-arg/env-var name must stay `PUBLIC_*` for Astro to inline it). One image is shared by staging + prod, so a `PUBLIC_*` value is identical across environments; a build-arg cannot be changed per-env without a rebuild. Setting such a value as a Fly runtime secret has no effect (the bundle is already built). **A value that legitimately differs per environment must therefore NOT be a `PUBLIC_*` build-arg.** The backend API URL is the case in point: it is **not** baked at build — the browser calls the backend **same-origin** through the webapp's in-app `/api/*` reverse proxy, and only the server-side **runtime** `API_ORIGIN` (set in `webapp/fly.{staging,production}.toml [env]`, distinct per app) tells the proxy where to forward. One image, two environments, no rebuild, no CORS. See `frontend-patterns.md` § Same-origin API proxy + `environment-config.md` `API_ORIGIN`.
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
