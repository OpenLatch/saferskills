---
paths:
  - "services/api/.env*"
  - "webapp/.env*"
  - "docker-compose*.yml"
  - "services/api/app/core/config.py"
  - "webapp/src/env.ts"
---

# Environment Config

> **Paths**: `services/api/.env*`, `webapp/.env*`, `docker-compose*.yml`, `services/api/app/core/config.py`, `webapp/src/env.ts`

## Purpose

All env vars are read through a typed wrapper — `pydantic-settings` on the backend, a Zod-validated `env.ts` module on the frontend. **Never read `os.environ` / `process.env` / `import.meta.env` directly in feature code.** This guarantees: typed access, default values in one place, fail-fast on missing required vars.

## W1 env vars

### Backend (`services/api/app/core/config.py`)

| Var | Required | Default | Purpose |
|---|---|---|---|
| `DATABASE_URL` | yes | (none) | PostgreSQL connection string (`postgresql+asyncpg://...`) |
| `SENTRY_DSN` | no | unset | Errors-only Sentry project (cf. `telemetry.md`) |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | no | unset | OpenTelemetry collector |
| `ENV` | yes | `development` | One of `development` / `staging` / `production` — drives Sentry env tag, log format, migration auto-run skip |
| `LOG_LEVEL` | no | `INFO` | Python logging level |
| `CORS_ALLOWED_ORIGINS` | yes | `http://localhost:4321` | Comma-separated origin list |
| `SCAN_SUBMIT_DAILY_LIMIT` | no | `10` | Max scan submissions per IP per 24h (D-FE-11) |
| `VENDOR_SESSION_SECRET` | yes (prod) | dev-insecure default | HS256 signing key for the vendor right-of-reply session JWT (`ss_vendor_session` cookie). The API is the sole verifier — the webapp stores the JWT opaquely and forwards it as a Bearer token. 32+ random bytes in prod; rotate quarterly (rotation only invalidates in-flight 15-min sessions). I-03 Phase C. |

### Frontend (`webapp/.env.example`)

Frontend env vars MUST be prefixed `PUBLIC_*` (Astro convention) to be exposed at build time. Anything not prefixed stays server-side only.

| Var | Required | Default | Purpose |
|---|---|---|---|
| `PUBLIC_API_URL` | yes | `http://localhost:8000` | Backend base URL |
| `PUBLIC_POSTHOG_KEY` | no | unset | Client-side PostHog project key |
| `PUBLIC_POSTHOG_HOST` | no | `https://eu.posthog.com` | PostHog ingestion host (EU region default) |
| `PUBLIC_SENTRY_DSN` | no | unset | Browser Sentry project |
| `RESEND_API_KEY` | no | unset | Outbound email (Resend) — server-only, NOT `PUBLIC_*`. Single verified sending domain `notifications.openlatch.ai` (shared with OpenLatch, cost decision 2026-05-28). Hardcoded `From:` in the send-call: `SaferSkills <<purpose>@notifications.openlatch.ai>`. Reply-to is a `@openlatch.ai` mailbox. |

## `.env.example` discipline

- **Every required var is documented** in the matching `.env.example` with a placeholder (`<set-me>` or a public-safe default).
- **No real secrets in `.env.example`** — `gitleaks` pre-commit hook enforces.
- **The example is the contract** — adding a runtime read of an undocumented var is rejected in review.

## Loading rules

- **Backend**: `pydantic-settings` reads from process env, then `.env` in dev. The `Settings` class is a frozen singleton (`@lru_cache`) imported as `from app.core.config import settings`. No re-instantiation, no override outside tests.
- **Frontend**: Astro reads `PUBLIC_*` vars at build time; `webapp/src/env.ts` re-exports a Zod-validated object. Components import `env` from there.
- **Tests**: backend tests override settings via `monkeypatch` on the singleton — never via raw `os.environ.setdefault`.

## Fly secret-staging rule (when deploy ships W2-W3)

When prod deploys land:

- **Always** use `flyctl secrets set --stage` followed by `flyctl deploy` in one job (per `ci-cd.md`). Never `flyctl secrets set` without `--stage` — that triggers an immediate roll that can apply new-shape secrets to a stale image.
- **Never split** `sync-secrets-*` from `deploy-*`. One atomic image-and-secrets roll per service per deploy.
- See `ci-cd.md` § Deployment for the full atomic-roll contract.

## Local dev (`docker-compose.yml`)

- Single compose file at repo root brings up postgres + api + webapp.
- Compose reads `.env` (gitignored) for dev overrides; the example lives at `.env.example` (committed).
- Override file `docker-compose.override.yml.example` shows how to point compose at an alternate Postgres / a local Resend stub.

## Hard rules

1. **Typed access only.** `app.core.config.settings` (backend) and `webapp/src/env.ts` (frontend) are the only entry points. No direct `os.environ` / `process.env` / `import.meta.env` outside those modules.
2. **`.env.example` is the contract.** New env var = new entry in the matching `.env.example` in the same PR.
3. **`PUBLIC_*` prefix means client-exposed.** Anything else is server-only. The Astro convention is non-negotiable.
4. **Fly secret-staging** when deploy lands. Never `flyctl secrets set` without `--stage` on production.

## When to update this rule

| Change | Updates here |
|---|---|
| New backend env var | "Backend" table + `services/api/.env.example` + `services/api/app/core/config.py` |
| New frontend env var | "Frontend" table + `webapp/.env.example` + `webapp/src/env.ts` |
| New secret stored in Fly | "Fly secret-staging rule" + `ci-cd.md` Deployment |
| New compose service | "Local dev" + root `docker-compose.yml` + `tech-stack.md` |
