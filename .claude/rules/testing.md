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

## E2E commands at W1

`tools/e2e/` is a Python Typer CLI that drives Playwright against an already-running stack (local dev OR a deployed preview). Three commands at W1:

| Command | Purpose |
|---|---|
| `doctor` | Sanity-check the test environment — base URL reachable, target host resolves, browser launches. Always green or always red; no flakes. |
| `smoke` | Smallest possible end-to-end — load the homepage, assert the page boots without JS errors, assert the API `/healthz` returns 200. |
| `homepage` | Hero copy + nav + footer + above-the-fold render assertions. |
| `item-detail` | Load `/items/<slug>` (slug discovered from the API); assert identity strip + score band render. Empty catalog → skip. (I-03 Phase C) |
| `vendor-respond` | Load `/items/<slug>/respond`; assert the unverified verify-challenge renders. Full redeem→submit is covered by `tests/routers/test_vendor.py`. Empty catalog → skip. (I-03 Phase C) |
| `badge-endpoint` | GET `/badge/<scan_id>/<score>.svg`; assert 200 + `image/svg+xml` + a tampered score → 400. No scans → skip. (I-03 Phase C) |
| `og-endpoint` | GET `/og/scan/<scan_id>.png`; assert 200 + `image/png` + PNG magic. No scans → skip. (I-03 Phase C) |
| `upload-flow` | `/scan` Upload tab default + DropZone + public-default toggle + consent; if a public upload item exists, its report shows upload provenance. Empty → skip. **Staging acceptance only**, not a required pr-checks lane (I-3.5). |
| `unlisted-flow` | Loopback-create an unlisted upload → `/scans/r/<token>` shows the private banner + manage bar + page-level `noindex` header & meta; delete → token 404s. Cap/non-loopback → skip. **Staging acceptance only** (I-3.5). |
| `catalog-badge-filter` | An unlisted shadow slug 404s on `/items/<slug>`; `/catalog` Source filter renders; if a public upload exists, the UPLOAD badge renders under `?artifact_source=upload`. **Staging acceptance only** (I-3.5). |
| `all` | Orchestrator — runs `doctor` → `smoke` → `homepage` → `item-detail` → `vendor-respond` → `badge-endpoint` → `og-endpoint` → `upload-flow` → `unlisted-flow` → `catalog-badge-filter` in sequence; fails fast on first red command. The I-3.5 commands skip gracefully on a fresh/empty staging, so they never hard-fail the sequence. |

Run locally via:

```bash
cd tools/e2e && uv sync
uv run saferskills-e2e all                     # defaults to http://localhost:4321
uv run saferskills-e2e all --base-url https://staging.saferskills.ai
```

Commands sequence is strict — `doctor` must pass before any other command runs (the orchestrator enforces).

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
| New E2E command | "E2E commands at W1" + `tools/e2e/README.md` |
| New coverage gate threshold | "Test pyramid" table + `ci-cd.md` lanes 6 / 7 |
| New factory directory | "Fixtures + factories" |
| New a11y violation tier rejected | "Test pyramid" component a11y row |
