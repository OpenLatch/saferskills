# Launch on-call runbook

> The launch-day incident playbook. Every command below is copy-pasteable and
> the Fly app names match the deployed services. This is a committed reference
> the on-call reads — not an outbox founder-action. Production deploys are
> **gated off until MVP** (`ENABLE_PRODUCTION_DEPLOYS` unset; prod Fly apps
> suspended), so during the launch window the live target is **staging**
> (`saferskills-{api,worker,webapp}-staging`); swap the `-staging` suffix once
> prod is resumed. See `.claude/rules/ci-cd.md` § Deployment.

## At a glance

| | |
|---|---|
| **On call** | Founder (Luc Delsalle). Single-operator launch. |
| **Services** | `saferskills-api[-staging]`, `saferskills-worker[-staging]`, `saferskills-webapp[-staging]` (Fly.io). The worker reuses the API image, run as `python -m app.worker_main`. |
| **Health** | `GET https://staging.saferskills.ai/api/v1/health` → `{status, ingestion: "ok"|"degraded"}`. The API self-degrades (503 on all routes but `/health`) rather than crash-loop. |
| **Alerts** | Slack (`SLACK_ALERTS_WEBHOOK_URL`) — ingestion + ops pages. Never Discord. |
| **Errors** | Sentry projects `saferskills-{api,webapp,cli}` on `https://de.sentry.io`. |
| **Analytics** | PostHog (cookieless, EU region) — bucketed, no PII. |
| **CLI** | `flyctl` only. Never any other host CLI. |
| **Status page** | Public `status.saferskills.ai` (Upptime — founder/outbox). In-app `500.astro` is the branded render-error page. |

## Two distinct failure surfaces (don't confuse them)

- **`500.astro`** — a webapp **page render** threw (SSR error). Fully static, fetches
  nothing, `noindex`. Sentry still captures it (the middleware re-throws after
  `captureException`).
- **`502 {"error":"upstream_unreachable"}`** — the webapp's same-origin `/api/*`
  reverse proxy (`webapp/src/pages/api/[...path].ts`) could not reach the backend.
  This is an API-JSON response on the proxy path, distinct from the 500 page.
  Backend-down shows up here, NOT as a 500 page.

## Incident scenarios

| Scenario | Detection | Response (real commands) |
|---|---|---|
| **Scan engine stalls** | Sentry `scan_timeout` / `scan_failed` spike; the Procrastinate `scan` queue depth grows; `/api/v1/health` → `ingestion: "degraded"` | Restart the **worker** machines (the worker drains the `scan` queue): `flyctl machine list --app saferskills-worker-staging --json \| jq -r '.[].id' \| while read m; do flyctl machine restart --app saferskills-worker-staging "$m"; done`. On boot the worker sweeps stalled `doing` jobs back to `todo`; the periodic `scan_stalled_retrier` (every 15 min) re-queues any the worker abandoned. If persistent, scale the worker pool (`flyctl scale count …`). |
| **Ingestion broken for one source** | Per-source success drops / `ingestion_cycle_failed` Slack + PostHog alert; `GET /api/v1/admin/sources/{source}/runs` history shows failures; `/api/v1/health` → `ingestion: "degraded"` | Pause that adapter so it stops failing — the catalog keeps growing from the other sources, users don't notice: `curl -X POST -H "X-Admin-Key: $SAFERSKILLS_ADMIN_KEY" -H 'content-type: application/json' -d '{"reason":"launch incident","contact":"oncall"}' https://staging.saferskills.ai/api/v1/admin/sources/{source}/pause`. Re-enable with `…/sources/{source}/unpause`. (Note the real path — **no `/ingestion/` segment**, param is `{source}`.) |
| **Frontend deploy regression** | Broken-page reports; Sentry `saferskills-webapp` spike | Roll back to a known-good image, then force-start stopped machines: `flyctl deploy --app saferskills-webapp-staging --image registry.fly.io/saferskills-webapp:main-<good-sha>`; then `flyctl machine list --app saferskills-webapp-staging --json \| jq -r '.[].id' \| while read m; do flyctl machine start --app saferskills-webapp-staging "$m" \|\| true; done`. Hotfix forward via a new PR (don't hand-patch Fly). **A dedicated rollback workflow is not yet built** — use this flyctl image path for both staging and prod. |
| **HN/PH traffic spike — latency climbs** | p95 homepage > 5s; Sentry; Fly metrics | The homepage + `/research` + marketing pages are **prerendered** (SSG), so they absorb read traffic without the backend. Scale machines: `flyctl scale count 2 --app saferskills-webapp-staging` (raise as needed; also scale `saferskills-api-staging` if scan-submit climbs). Scans queue rather than 5xx; let the queue drain. |
| **Agent-scan grader hangs / backs up** | Grading queue depth grows; runs stuck in `submitted` | Restart the worker (as in "scan engine stalls" — same machines). If persistent, stop accepting new agent-scan run-creates (capability scans unaffected) and post a status notice; no partial reports ship (grading is all-or-nothing). |
| **Per-run canary rotation fails** | `tamper-suspected` spike / canary-derivation errors | Halt agent-scan run-creates. Verify the HKDF master key `SAFERSKILLS_AGENT_MASTER_KEY` + the pack-signing key are present (`flyctl secrets list --app saferskills-api-staging`). The design is fail-closed: offline keys hard-fail and the scan aborts cleanly — it never mis-grades. Re-enable once healthy. **Do not regenerate `SAFERSKILLS_AGENT_MASTER_KEY`** — it breaks already-shipped CLI verification. |
| **API degraded (DB unreachable)** | `/api/v1/health` 503 on all routes but `/health`; `StartupGuardMiddleware` engaged | The API self-degrades (503 except `/health`) rather than crash-loop. Check the Postgres app health (find its name first — see the DB-wedged row); a `flyctl machine restart --app saferskills-api-staging <id>` re-runs `alembic upgrade head` under the `pg_advisory_lock` (`0x5AFE5C11`) on boot. |
| **DB process wedged** | health 503; connections pile up; ingestion frozen | First **discover the Postgres app name** (it is provisioned manually, not committed in this repo): `flyctl postgres list` (or `flyctl apps list \| grep -i postgres`). Then restart its machine: `flyctl machine list --app <that-app> --json \| jq -r '.[].id'` → `flyctl machine restart --app <that-app> <machine-id>` (the recovery path from the staging ingestion incident). Confirm `/api/v1/health` returns to `ok` afterward. |

## Watch during the launch window

- **Health**: `watch -n30 'curl -s https://staging.saferskills.ai/api/v1/health'` — `status` + `ingestion`.
- **Slack alerts channel** (`SLACK_ALERTS_WEBHOOK_URL` sink) — ingestion/ops pages.
- **Sentry** `saferskills-api` + `saferskills-webapp` (de.sentry.io) — error rate, new issues.
- **Fly metrics** — per-app machine CPU/RAM + restarts (the API is RAM-bound; a worker OOM must not take the API down — that's why they're split services).
- **Scan throughput** — the catalog grows at the speed of real scans; a flat count means the worker is stuck (see "scan engine stalls").

## Deferred (not this round)

- **Pre-launch load test (L-1 / L-2)** — DEFERRED to `outbox/06` (D-07-09). k6 is the lean when built. DoD L-1/L-2 stay open.
- **Public status page** — `status.saferskills.ai` is an Upptime setup owned by the founder/outbox (outbox/02), not in this repo.

## Safety notes

- **Fix in code, not on infra.** Durable fixes ship via CI/PRs. Do not hand-patch
  Fly with `flyctl secrets set` / `machine --env` toggles or manual DB surgery —
  a redeploy drops them. The flyctl commands above are for *recovery* (restart,
  rollback, scale, pause), never for persistent config changes.
- **Secrets are CI-staged.** `deploy.yml` is the source of truth for every deploy
  secret; setting one by hand drifts from CI.
- **Admin mutations are audited.** Every `POST /api/v1/admin/*` writes one
  `admin_audit_log` row — see `.claude/rules/security.md` § Audit Trail.
