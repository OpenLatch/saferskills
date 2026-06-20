# CI/CD Requirements

All checks must pass before merge. Every third-party action is **SHA-pinned** (never floating tags); the first step of every workflow is `step-security/harden-runner`; every workflow declares `permissions: contents: read` at the top and elevates per-job only when needed.

## Pipeline lanes (15 + 5 Rust CLI + `all-checks` aggregation)

`pr-checks.yml` runs 15 web/backend lanes + 5 Rust CLI lanes plus the aggregator (13 core lanes + `lighthouse-a11y` + `docs-build` + the 5 `cli-*` lanes). The native docs (no separate Starlight build) prerender as part of the main webapp build, so the build-dependent docs gates (llms.txt + internal links + the docs axe spec) run inside `lighthouse-a11y`; `docs-build` is now just the fast frontmatter gate. Tools are SHA-pinned in `.github/actions/` reusable composites.

| # | Lane | What it does |
|---|---|---|
| 1 | `validate` | JSON Schema validation (ajv-cli), schema-to-code generation drift check (runs all 9 generators: regenerates the ingestion source-registry from `config/sources/*.yaml` + Pydantic + SQLAlchemy + `openapi.json` + TS DTOs + Zod + methodology + the **agent-pack** from `rubric/AGENT/*.md`; fails if `git diff --exit-code` is non-empty — this catches a provider YAML or rubric file added without `pnpm run generate`), **outbound-host allowlist** (`node scripts/validate-outbound-allowlist.cjs` — self-derived from the YAML `hosts:` lists; every host an adapter `.py` fetches must be declared in some provider YAML), no-CDN-fonts grep, placeholder-taxonomy grep, and **CSS token discipline** (`node scripts/check-css.cjs` — no stale `var(--x,#hex)` fallbacks, no undefined tokens, no raw hex in shell page CSS; see `design-system.md` § CSS token discipline) |
| 2 | `lint-fe` | Biome (`pnpm biome check .`) — TS/JS/JSON |
| 3 | `lint-be` | Ruff (`uv run ruff check . && uv run ruff format --check .`) |
| 4 | `typecheck-fe` | `pnpm astro check` + `pnpm tsc --noEmit` |
| 5 | `typecheck-be` | `uv run pyright` |
| 6 | `test-fe` | Vitest (≥70% line coverage) |
| 7 | `test-be` | pytest (≥70% line coverage) |
| 8 | `ladle-build` | `pnpm ladle:build` — catches broken stories, missing imports, render errors. Runs on PRs touching `ui/` or `webapp/src/components/` |
| 9 | `docker-build` | Parallel matrix (api + webapp) with scoped GHA cache. **Both** images build from a **repo-root context** — the API image needs it to `COPY rubric/` (the scan engine loads its rules from the repo-root `rubric/` tree at runtime; outside `services/api/`). CI stamps `RUBRIC_VERSION`/`ENGINE_VERSION` (rubric/ + scan-engine subtree SHAs) as build-args so the reconcile re-evals only on a rule/engine change. |
| 10 | `docker-smoke` | `docker compose -f ci/docker-compose.smoke.yml up` — postgres + api + webapp boot + `/healthz` 200, **then asserts the API image loaded its rubric** (`_load_all_rules() ≥ 1`) — regression guard for the root-context `COPY rubric/` (a missing rubric loads 0 rules → every scan a fake 100, invisible to `/health`). |
| 11 | `trivy-scan` | Trivy vulnerability scanner (CRITICAL/HIGH) with SARIF upload to GitHub Security tab |
| 12 | `dep-scan` | `pip-audit` (`uv pip compile`) + `pnpm audit --audit-level=high` |
| 13 | `pr-title-lint` | Conventional Commits format check |
| 14 | `lighthouse-a11y` | `@lhci/cli` (Lighthouse, **observe-mode `warn`** on the no-seed public pages — reports uploaded, not yet hard-gating; promote categories to `error` once perf is baselined in this CI env) + `@axe-core/playwright` WCAG 2 A/AA smoke as the **hard** a11y gate. Runs on PRs touching `webapp/**` or `ui/**` (gated on `detect-changes.outputs.frontend`). Brings up postgres+api from the smoke compose, builds + serves the webapp Node SSR on :5173 (`--no-sandbox` Chrome). The native docs prerender into `dist/client/docs` as part of that build, so this lane ALSO carries the docs build-artifact gates — llms.txt/llms-full.txt/pagefind non-empty + `node scripts/check-internal-docs-links.cjs` (no broken `/docs/*` link) — and its axe step runs BOTH `pages.spec.ts` + `docs.spec.ts` (docs P0 pages, served on the same :5173). Docs P0 pages are also in `.lighthouserc.json` (observe-warn). Seeded pages (item-detail / scan-report) are Lighthoused **post-deploy** in the `e2e-staging` job (see Deployment — SEO-T6 staging lhci step), not here — the PR lane's postgres is empty so an item/scan URL 404s. |
| 15 | `docs-build` | Fast docs frontmatter gate: `node scripts/validate-docs-frontmatter.cjs` — every page under `webapp/src/content/docs/**` carries `title` + `description` (+ optional `order`/`sidebarLabel`). No build/API needed; the build-dependent docs gates run in `lighthouse-a11y` (above). Gated on a `docs` paths-filter (`webapp/src/content/docs/**` + `webapp/src/content.config.ts` + `webapp/src/components/docs/**` + `webapp/src/layouts/DocsLayout.astro` + `webapp/src/styles/page-docs.css` + `webapp/src/lib/docs/**` + `webapp/src/pages/docs/**` + the agent manifest + the docs scripts/test) |
| 16 | `cli-fmt` | `cargo fmt --manifest-path cli/Cargo.toml --all --check` |
| 17 | `cli-clippy` | `cargo clippy --manifest-path cli/Cargo.toml --all-targets -- -D warnings` |
| 18 | `cli-test` | `cargo llvm-cov` test + **≥70% line coverage** (`--fail-under-lines 70`) |
| 19 | `cli-build` | `cargo build --release` + **<15 MB** size gate on the `saferskills` binary |
| 20 | `cli-rustls` | `cargo tree -e normal` must contain no `openssl-sys` / `native-tls` — the rustls-only invariant. The `scan agent` deps (`ed25519-dalek` verify-only, `base64`) are pure-Rust and pull neither, so the lane stays green |
| – | `all-checks` | Aggregation job — gates merge; depends on all 20 |

The 5 `cli-*` lanes gate on a `dorny/paths-filter` `cli` matcher (`cli/**` + `.github/actions/setup-rust/**`) and use the `.github/actions/setup-rust` composite (toolchain + `cli/`-scoped cargo cache). The `docs-build` lane gates on the `docs` paths-filter and reuses the `.github/actions/setup-saferskills-build` composite; the build-dependent docs gates ride in `lighthouse-a11y` (gated on `frontend`, which docs changes under `webapp/**` also trip). Both smoke + build lanes gate positively on a `dorny/paths-filter` `changes` matcher (`backend`/`frontend`/`schemas`/`ci`); they skip only when the PR is **pure docs**. Mixed code+docs PRs run the full pipeline.

## Always-on workflows

| File | Cadence | Purpose |
|---|---|---|
| `scorecard.yml` | Weekly + on push to `main` | OpenSSF Scorecard — publishes to `securityscorecards.dev` and SARIF |
| `release-please.yml` | On push to `main` | **Dormant for now** (no `v1.0.0` release yet); flips on first tagged release |
| CodeQL (UI default-setup) | On PR + nightly | Static analysis for Python + TypeScript |

## CLI release + publish

The `saferskills` install CLI (a Rust crate in `cli/`) is the **only** `release-please`-managed package, so its tag is the bare `vX.Y.Z` (no component prefix; `include-component-in-tag: false`).

- **release-please**: `release-please-config.json` sets the `cli` package `release-type: "rust"` — it bumps `cli/Cargo.toml` + `cli/Cargo.lock` + `cli/CHANGELOG.md`. Merging the Release PR (via the `version-bump.yml` GitHub-App token) tags `vX.Y.Z`.
- **`publish-npm.yml`** (filename is load-bearing — the npm + crates.io Trusted-Publisher bindings verify it): on the tag it builds the **5-target matrix** (`aarch64`/`x86_64` Apple, `x86_64`/`aarch64` Linux via `cross`, `x86_64` Windows) with `--features crash-report,telemetry-network`, **baking** `SAFERSKILLS_POSTHOG_KEY` (from the GH Actions secret `POSTHOG_PROJECT_KEY` — the canonical name shared with the backend + webapp) + `SAFERSKILLS_SENTRY_DSN` (from `SENTRY_DSN_CLI`) + `SAFERSKILLS_PACK_PUBKEY` (the Agent Scan pack-verify pubkey map, from the repo-level secret `PACK_PUBKEY`; empty → `scan agent` skips pack verification with a warning) via `build.rs` (`Cross.toml` passes all through to the cross containers), size-gates each (<15 MB), uploads **debug symbols** to the `saferskills-cli` Sentry project (`sentry-cli debug-files upload --include-sources`, `SENTRY_URL=https://de.sentry.io`, `SENTRY_AUTH_TOKEN` — non-fatal/skipped when unset; symbols are separated by `split-debuginfo="packed"`), cosign-keyless-signs + Syft-SBOMs the binaries, uploads them to the GitHub Release, then: stamps + publishes the 5 scoped `@openlatch/saferskills-<platform>` packages **before** the unscoped `saferskills` main package (OIDC, no `NPM_TOKEN`), `cargo publish --manifest-path cli/Cargo.toml` (crates.io OIDC), and a 3-OS `verify-publish` smoke (`--version` / `--help` / `completion`). `workflow_dispatch` is build-only (never publishes). Both telemetry/crash bakes are **optional** — an unset secret ships the binary with that channel inert (empty bake → hard no-op).
- **Founder action (one-time)**: the 6 npm TP bindings + the crates.io TP binding → `publish-npm.yml`; `npm deprecate @openlatch/saferskills`. Provenance needs a public repo. The observability secrets (`POSTHOG_PROJECT_KEY`, `SENTRY_DSN_CLI`, `SENTRY_AUTH_TOKEN`) are repo-level GH Actions secrets.

## Post-Implementation Verification

After completing a feature, fixing a bug, or refactoring — and before opening a PR — run `/verify-build`. It auto-detects changed layers and runs the appropriate quality gates (build, typecheck, lint, tests). A session that leaves broken checks is a failed session.

## Deployment (staging live, prod gated until MVP)

Staging deploys on every push to `main` via `deploy.yml` (`deploy-staging-api` / `deploy-staging-worker` / `deploy-staging-webapp` → `saferskills-{api,worker,webapp}-staging`) and is followed by `e2e-staging` Playwright smoke. **SEO-T6 staging Lighthouse**: the `e2e-staging` job has a second, non-blocking step (`continue-on-error`) that Lighthouses the two real money-pages — the newest public catalog item + its newest public scan run — on **populated** staging. It resolves the two live URLs at run time (`curl` `GET $API/api/v1/items?limit=1` + `/scans?limit=1`, `jq` them into `.lighthouserc.staging.json` → `.lighthouserc.staging.run.json`), falling back to the homepage when staging is empty, then runs `npx @lhci/cli autorun`. **Observe-warn only** (same INP/LCP/CLS budgets as `.lighthouserc.json`) so a perf blip never red-gates a deploy; these pages can't be Lighthoused in the PR `lighthouse-a11y` lane (empty postgres 404s an item/scan URL). Production deploys are **gated off until SaferSkills reaches MVP state**: the prod jobs only run when the repo variable `ENABLE_PRODUCTION_DEPLOYS` equals `"true"` (currently unset). In parallel, the prod Fly apps `saferskills-api` / `saferskills-worker` / `saferskills-webapp` are kept in `suspended` state with zero machines — flipping the variable alone is not sufficient, a maintainer must also `flyctl apps resume` before the first prod deploy lands. When that happens:

- **The worker is a third service that reuses the API image.** `services/worker/` is config-only (no build) — its `deploy-staging-worker` / `deploy-production-worker` jobs `flyctl deploy --config fly.<env>.toml --image registry.fly.io/saferskills-api:main-<sha>` (the SAME image bytes as the API, dual-registry discipline preserved) with `python -m app.worker_main` as the process command. It is gated on a `worker` paths-filter (`services/api/**` + `schemas/**` + `services/worker/**`) and uses `FLY_API_TOKEN_API` (must be org-scoped to cover the worker app + registry pull; else mint `FLY_API_TOKEN_WORKER`). It stages the four boot-guard secrets (`TURNSTILE_SECRET_KEY`, `SAFERSKILLS_CLI_POW_SECRET`, `SAFERSKILLS_AGENT_MASTER_KEY`, `SAFERSKILLS_PACK_SIGNING_KEY`) + observability + Slack + the optional `SAFERSKILLS_INDEXNOW_KEY[_LOCATION]` (the IndexNow ping runs in the WORKER's `ping_indexnow` Procrastinate task, so the worker — not the API — needs the key; staged guarded/skipped-when-unset like `SENTRY_DSN`. **It is a `production`-environment-scoped GH secret, not repo-level**: the key + `keyLocation` bind to the live `saferskills.ai` domain, so IndexNow is prod-only — the `deploy-staging-worker` job runs in `environment: staging`, sees the secret as empty, and its guarded block no-ops, so staging never pings. The verification file is committed at `webapp/public/<KEY>.txt`), but **NOT** the HTTP-route-only `SAFERSKILLS_ADMIN_KEY` / `SAFERSKILLS_PROXY_SHARED_SECRET`. The API apps set `INGESTION_WORKER_ENABLED=false` in their `fly.*.toml [env]` so only this worker process runs the Procrastinate worker. Non-CI secrets (`DATABASE_URL`, `GITHUB_APP_*`) are set once manually on the worker app (as on the API). See `services/worker/README.md` + `ingestion.md` § Procrastinate worker.

- **Unified pipeline** (`deploy.yml`): push to `main` → build ALL images → deploy staging (path-filtered) → smoke → deploy production (canary, atomic image+secrets, 5-min soak, auto-rollback on failure).
- **Production canary**: `fly.production.toml` uses `strategy = "canary"` — boots one Machine first, health-checks it, auto-aborts on failure.
- **Production deploys are always-all-services**: every approved prod deploy ships all three services (api + worker + webapp) at the current `main` SHA, regardless of path filter. Prevents stale-image drift.
- **Atomic image + secrets roll**: `flyctl secrets set --stage ...` + `flyctl deploy --image registry.fly.io/saferskills-<svc>:main-<sha>` in one job per service. Never split `sync-secrets-*` from `deploy-*`. The API deploy jobs stage `TURNSTILE_SECRET_KEY` (from the GH Actions secret of the same name, skipped when unset) before `flyctl deploy` so the secret + image land in one release. With `ENV=production` the API startup guard **requires** that secret — set the GH secret before the first prod deploy. The deploy jobs also stage `SAFERSKILLS_PROXY_SHARED_SECRET` (from the GH Actions secret of the same name, skipped when unset) — on **both** the API app **and** the webapp app, since the value must be identical: it is how the API trusts the webapp `/api/*` proxy's forwarded visitor IP (the proxy sends it as `X-Proxy-Secret`). On the webapp it is a server-side **runtime** secret (the Node proxy reads it at request time), NOT a build-arg. The API deploy jobs additionally stage `SAFERSKILLS_ADMIN_KEY` (API apps only — the webapp does not use it; skipped when unset) — gating `/api/v1/admin/*`. Unlike the two above, it is an **environment-scoped** GH Actions secret (same name, distinct value per env: the staging job runs in `environment: staging`, the prod job in `environment: production`); without it the admin gate fails closed (403) since deploys always set `ENV` (the keyless exemption is local-dev only). The API deploy jobs also stage `SLACK_ALERTS_WEBHOOK_URL` (API apps only — the page-tier sink for ingestion alerts, `app/ingestion/framework/alerts.py`; skipped when unset). Unlike `SAFERSKILLS_ADMIN_KEY`, it is a **repo-level** GH Actions secret (same value both envs, like `TURNSTILE_SECRET_KEY` — the single Slack incoming-webhook is bound to one channel); unset → alerts degrade to Sentry/PostHog only (no Slack page), never a boot failure. **Set it via the GH Actions secret, not a manual `flyctl secrets set`** — CI is the source of truth so a redeploy never drops it. The API deploy jobs also stage `SLACK_INVITE_URL` (API apps only — the `/api/v1/community/slack/redirect` target + the invite health-probe input, both web-tier; skipped when unset). Like `SLACK_ALERTS_WEBHOOK_URL` it is a **repo-level** GH Actions secret (same value both envs); the value is semantically public (a never-expire Slack join link) but is shipped as a secret to keep it out of git + rotatable without a commit; unset → the redirect 503s + the health loop no-ops, never a boot failure. The API deploy jobs also stage `SAFERSKILLS_CLI_POW_SECRET` (API apps only; from the GH Actions secret of the same name, skipped when unset) — the trust anchor of the stateless CLI Proof-of-Work scan-submit gate. Like `TURNSTILE_SECRET_KEY`, the API startup guard **requires** it under `ENV=staging`/`production`, so set the GH secret before the first such deploy; it must be a **stable** value (identical across canary machines), never per-process random. The API deploy jobs also stage the **observability** secrets (all optional, skipped when unset, degrade to structlog-only — never a boot failure): `SENTRY_DSN` (from the env-scoped GH secret `SENTRY_DSN_API`), `POSTHOG_PROJECT_KEY`, and `POSTHOG_SERVER_KEY` (env-scoped); `POSTHOG_HOST` + the `OTEL_*` trace config are non-secret `[env]` in the API `fly.*.toml`. The **webapp** deploy jobs additionally stage the server-side runtime `SENTRY_DSN` (from `SENTRY_DSN_WEBAPP`) for the SSR/proxy Sentry (`src/middleware.ts`); the webapp `ENV` tag is `[env]` in its `fly.*.toml`. See `security.md` § Public-input handling #11 + #12 + Audit Trail + `telemetry.md` § Sentry/OpenTelemetry + `environment-config.md`.
- **Build-time public config (`PUBLIC_*`) is a build-arg, not a Fly secret**: `PUBLIC_*` values are inlined into the Astro bundle at `pnpm build` (inside the webapp image build), so they must be passed as Docker `--build-arg`s in the `build-and-push` job — `GIT_SHA` (also re-exported in-Dockerfile as `PUBLIC_GIT_SHA` for the Sentry browser release), `PUBLIC_TURNSTILE_SITE_KEY` (declared `ARG` in `webapp/Dockerfile`, valued from the GH Actions secret **`TURNSTILE_PUBLIC_SITE_KEY`** — the secret is `TURNSTILE_`-grouped, but the build-arg/env-var name must stay `PUBLIC_*` for Astro to inline it), plus the observability build-args `PUBLIC_SENTRY_DSN` (from `SENTRY_DSN_WEBAPP`) + `PUBLIC_POSTHOG_KEY` (from `POSTHOG_PROJECT_KEY`) + `PUBLIC_POSTHOG_HOST`. The Sentry **source-map upload** runs inside the webapp image build keyed to `GIT_SHA`, using `SENTRY_AUTH_TOKEN` mounted as a **BuildKit secret** (`--mount=type=secret,id=sentry_auth_token`, passed via the `secrets:` input of `docker/build-push-action`) so the token never lands in an image layer; it no-ops when the secret is empty. One image is shared by staging + prod, so a `PUBLIC_*` value is identical across environments; a build-arg cannot be changed per-env without a rebuild. Setting such a value as a Fly runtime secret has no effect (the bundle is already built). **A value that legitimately differs per environment must therefore NOT be a `PUBLIC_*` build-arg.** The backend API URL is the case in point: it is **not** baked at build — the browser calls the backend **same-origin** through the webapp's in-app `/api/*` reverse proxy, and only the server-side **runtime** `API_ORIGIN` (set in `webapp/fly.{staging,production}.toml [env]`, distinct per app) tells the proxy where to forward. One image, two environments, no rebuild, no CORS. See `frontend-patterns.md` § Same-origin API proxy + `environment-config.md` `API_ORIGIN`.
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
| New service shipped | "Deployment" — re-verify always-all-services + force-start loop |
| New dependency-bump source | "Dependency-bump policy" |
| New pre-commit hook | "Pre-Commit Hooks" |
