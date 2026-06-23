---
paths:
  - "**/tests/**"
  - "**/test/**"
  - "**/*.test.{ts,tsx,py}"
  - "tools/e2e/**"
  - "ui/test/**"
---

# Testing

> **Paths**: `**/tests/**`, `**/test/**`, `**/*.test.{ts,tsx,py}`, `tools/e2e/**`, `ui/test/**`

## Test pyramid

| Layer | Tool | Coverage gate | Where |
|---|---|---|---|
| **Unit — backend** | pytest | ≥70% line coverage in CI | `services/api/tests/` |
| **Unit — frontend** | Vitest 4 | ≥70% line coverage in CI | `webapp/test/` + `ui/test/` |
| **Component a11y smoke** | vitest-axe | No `serious`/`critical` violations | `ui/test/components/**` |
| **Story render** | Ladle build | Build must succeed | `ui/stories/**` |
| **E2E** | Playwright 1.60 | All commands green | `tools/e2e/` |

Coverage gates are enforced in `pr-checks.yml` (`test-fe` / `test-be` lanes). The threshold is per-package; new code on a failing-coverage package must keep the package above 70% or land additional tests.

## E2E commands

`tools/e2e/` is a Python Typer CLI that drives Playwright against an already-running stack (local dev OR a deployed preview). The commands:

| Command | Purpose |
|---|---|
| `doctor` | Sanity-check the test environment — base URL reachable, target host resolves, browser launches. Always green or always red; no flakes. |
| `smoke` | Smallest possible end-to-end — load the homepage, assert the page boots without JS errors, assert the API `/healthz` returns 200. |
| `homepage` | Hero copy + nav + footer + above-the-fold render assertions. |
| `item-detail` | Load `/items/<slug>` (slug discovered from the API); assert the page-head identity title renders. Empty catalog → skip. |
| `vendor-respond` | Load `/items/<slug>/respond`; assert the unverified verify-challenge renders. Full redeem→submit is covered by `tests/routers/test_vendor.py`. Empty catalog → skip. |
| `badge-endpoint` | GET `/badge/<scan_id>/<score>.svg`; assert 200 + `image/svg+xml` + a tampered score → 400. No scans → skip. |
| `og-endpoint` | GET `/og/scan/<scan_id>.png`; assert 200 + `image/png` + PNG magic. No scans → skip. |
| `upload-flow` | `/scan` Upload tab default + DropZone + public-default toggle + consent; if a public upload item exists, its report shows upload provenance. Empty → skip. **Staging acceptance only**, not a required pr-checks lane. |
| `unlisted-flow` | Loopback-create an unlisted upload → `/scans/r/<token>` shows the private banner + manage bar + page-level `noindex` header & meta; delete → token 404s. Cap/non-loopback → skip. **Staging acceptance only**. |
| `scan-completes` | **Scan-pipeline regression guard** (API-level, no browser). Submits a tiny unlisted upload and polls `GET /scans/runs/<id>` to a terminal state, asserting `status='completed'` + `capability_count≥1` — the exact invariant the asyncpg-NOTIFY-pool failure broke (every scan died `failed` with nothing persisted; bulk auto-scan never touches that pool, so only a real SUBMIT exercises it). Submit works on loopback (cap-exempt), on staging (always-pass Turnstile test secret accepts the dummy `Cf-Turnstile-Response`), and SKIPS on prod (real secret rejects the dummy) or any rate-cap. Eagerly deletes the unlisted run. **Staging acceptance only**. |
| `catalog-badge-filter` | An unlisted shadow slug 404s on `/items/<slug>`; `/catalog` Source filter renders; if a public upload exists, the UPLOAD badge renders under `?artifact_source=upload`. **Staging acceptance only**. |
| `all` | Orchestrator — runs `doctor` → `smoke` → `homepage` → `item-detail` → `vendor-respond` → `badge-endpoint` → `og-endpoint` → `upload-flow` → `unlisted-flow` → `scan-completes` → `catalog-badge-filter` in sequence; fails fast on first red command. The upload/unlisted/scan-completes commands skip gracefully on a fresh/empty or human-gated staging, so they never hard-fail the sequence. |

Run locally via:

```bash
cd tools/e2e && uv sync
uv run saferskills-e2e all                     # defaults to http://localhost:4321
uv run saferskills-e2e all --base-url https://staging.saferskills.ai
```

Commands sequence is strict — `doctor` must pass before any other command runs (the orchestrator enforces).

### Transient-retry resilience (transient vs sustained)

The data-plane HTTP calls (catalog/scan discovery + the badge/OG fetches) go through `shared/http_client.request_with_retries`, which retries **only transient failures** — a `502/503/504` or a connect/read timeout — with exponential backoff (`--retries`, default 3; `--retry-backoff`, default 1.0s; per-request read timeout `request_timeout_seconds`, default 20s). This absorbs a momentary staging blip (e.g. the shared Postgres saturating for a few seconds under ingestion load) so a transient hiccup never red-gates a prod deploy. It deliberately does **not** mask a sustained outage: a `4xx`, any other status, or a still-degraded API after the last attempt is returned/raised as-is, so a sustained degradation still returns the failure exit code and blocks the deploy (the chosen contract — the full e2e gate stays in place). The `e2e-staging` deploy job adds one coarse re-run on top as defense-in-depth. The wrapper is unit-tested in `tools/e2e/tests/test_http_retries.py` (retries-then-succeeds vs sustained-still-fails). See `tools/e2e/README.md` § Resilience.

## Test-first culture (regression gate)

Every bug fix MUST land with a regression test that fails on `main` and passes on the fix branch. The PR description names the test that proves the bug is closed. A bug-fix PR with no regression test is rejected.

This is a hard rule even for cosmetic fixes — a visual regression closes a Ladle story diff or a vitest-axe gate; a layout fix closes a snapshot test.

## Async / network discipline

- **Backend tests** use `pytest-asyncio` + `httpx.AsyncClient` against an in-process FastAPI app (no live server). Database fixtures use a per-test transaction that rolls back at teardown.
- **Frontend tests** mock fetch via `vitest`'s built-in module mocking — never hit a real network. Use `msw` only if a test specifically needs HTTP-level interception.
- **E2E** is the only layer that hits a real server. Every E2E command names the base URL it targets and never assumes a fixture.

## Fixtures + factories

- Backend: factories live in `services/api/tests/factories/`. Use Polyfactory / Pydantic factories — never hand-roll dicts.
- Frontend: factories live in `webapp/test/factories/`. Reuse the same Zod schemas the runtime code uses; generate via `@anatine/zod-mock` or hand-rolled builders for stability.
- Snapshot tests are allowed for stable serialized output (JSON envelopes, audit-event shapes). Banned for HTML / Tailwind class strings — those churn too fast.

## Hard rules

1. **Coverage ≥70%** per package. New code must not drop the package below the floor.
2. **Bug fixes ship with a regression test.** No exceptions.
3. **`doctor` first** — every `tools/e2e/` orchestration sequence runs `doctor` before any other command.
4. **No real network in unit tests.** Mock at the HTTP-client boundary.
5. **No snapshot of Tailwind class strings** — class order is not stable across Tailwind versions.

## When to update this rule

| Change | Updates here |
|---|---|
| New E2E command | "E2E commands" + `tools/e2e/README.md` |
| New coverage gate threshold | "Test pyramid" table + `ci-cd.md` lanes 6 / 7 |
| New factory directory | "Fixtures + factories" |
| New a11y violation tier rejected | "Test pyramid" component a11y row |
