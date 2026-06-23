<div align="center">

<a href="../../README.md">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="../../webapp/public/logos/saferskills-dark-wordmark.svg">
    <img alt="SaferSkills" src="../../webapp/public/logos/saferskills-light-wordmark.svg" height="38">
  </picture>
</a>

<h3>End-to-end tests</h3>
<p>Playwright + async-Python orchestrator that validates a running stack.</p>

</div>

## What it is

The end-to-end test orchestrator for the SaferSkills platform — a small async Python CLI that validates service reachability, HTTP contracts, and the public site against a running stack (local Docker, staging, or production).

## Setup

```bash
cd tools/e2e
uv sync
uv run playwright install chromium
```

The first `playwright install chromium` downloads a versioned headless Chromium into Playwright's cache (`~/.cache/ms-playwright` on Linux/macOS, `%LOCALAPPDATA%\ms-playwright` on Windows). Re-running is a no-op once the binary is present. CI runs this step explicitly before invoking the suite; locally the `homepage` and `all` commands surface a clear error if the browser is missing.

## Commands

| Command | What it checks | Auth |
|---|---|---|
| `doctor` | API + base-URL reachability, per-target latency. | None |
| `smoke` | `GET /api/v1/health` returns `{"status":"ok"}` and `/openapi.json` is parseable. | None |
| `homepage` | Playwright loads `<base_url>`, asserts wordmark + email capture, screenshots. | None |
| `item-detail` | Playwright loads `/items/<slug>` (slug from the API); asserts identity + score band. Empty catalog → skip. | None |
| `vendor-respond` | Playwright loads `/items/<slug>/respond`; asserts the verify-challenge renders. Empty catalog → skip. | None |
| `badge-endpoint` | HTTP: `/badge/<scan_id>/<score>.svg` → 200 + SVG; tampered score → 400. No scans → skip. | None |
| `og-endpoint` | HTTP: `/og/scan/<scan_id>.png` → 200 + PNG magic for a COMPLETED scan (the endpoint 404s a pending/running/failed run). No completed scan → skip. | None |
| `upload-flow` | `/scan` Upload tab default + DropZone + public toggle + consent; upload report provenance if present. Empty → skip. (staging) | Chromium |
| `unlisted-flow` | Loopback-create an unlisted upload → `/scans/r/<token>` private banner + manage bar + `noindex` header/meta; delete → token 404s. Cap → skip. (staging) | Chromium |
| `scan-completes` | **Regression guard for the scan pipeline**: submit a tiny unlisted upload (loopback-exempt / staging always-pass Turnstile test secret / prod real-secret → skip) and poll the run to a terminal state, asserting `status=completed` with `capability_count≥1` — catches the asyncpg-pool failure where every scan died `failed`. Eagerly deletes the run. Cap / human-gate → skip. (staging) | None |
| `catalog-badge-filter` | Unlisted slug 404s on `/items/<slug>`; `/catalog` Source filter renders; UPLOAD badge under `?artifact_source=upload` if present. (staging) | Chromium |
| `all` | Runs every command above in sequence, stops on first failure (the upload/unlisted commands skip gracefully on empty staging). | None |

## Usage

```bash
uv run saferskills-e2e doctor
uv run saferskills-e2e smoke
uv run saferskills-e2e homepage
uv run saferskills-e2e all

# Override targets from the CLI (CLI flags win over env)
uv run saferskills-e2e doctor \
    --api-url  https://api-staging.saferskills.ai \
    --base-url https://staging.saferskills.ai

# Tune transient-retry resilience (defaults: 3 attempts, 1.0s base backoff)
uv run saferskills-e2e all --retries 5 --retry-backoff 2.0
```

## Resilience (transient vs sustained)

The data-plane HTTP calls (the catalog/scan discovery in `shared/discovery.py` and
the badge/OG fetches) go through `shared/http_client.request_with_retries`, which
**retries only transient failures** — a `502/503/504` or a connect/read timeout —
with exponential backoff (`--retries`, default 3; `--retry-backoff`, default 1.0s).
The per-request read timeout is **20s** (`request_timeout_seconds`).

This absorbs a momentary staging blip (e.g. the shared Postgres saturating for a few
seconds under ingestion load) so a transient hiccup never red-gates a prod deploy. It
deliberately does **not** mask a sustained outage: a `4xx`, any other status, or a
still-degraded API after the last attempt is returned/raised as-is, so real breakage
still fails the command. The `e2e-staging` deploy job adds one coarse re-run on top as
defense-in-depth.

## Environment

| Variable | Default | Purpose |
|---|---|---|
| `SAFERSKILLS_API_URL` | `http://localhost:8000` | FastAPI backend root URL. |
| `SAFERSKILLS_BASE_URL` | `http://localhost:5173` | Public site root URL. |

CLI flags `--api-url` / `--base-url` override the env vars when both are present. Screenshots are written under `<repo_root>/.local/screenshots/`.

## Exit codes

| Code | Meaning |
|---|---|
| `0` | All assertions passed. |
| `10` | A target was not reachable. |
| `11` | `/api/v1/health` regressed. |
| `12` | `/openapi.json` regressed. |
| `13` | Homepage assertions regressed. |
| `20` | Bad config (missing URL, etc.). |
| `99` | Unhandled error. |

`all` propagates the exit code of the first failing sub-command.

See [`tools/e2e/CLAUDE.md`](./CLAUDE.md) for the architecture + standards (strict-async, Pydantic-typed) and how to add a command.

---

<sub>Part of **[SaferSkills](../../README.md)** — every AI capability, independently scanned. · An [OpenLatch](https://openlatch.ai) project · [saferskills.ai](https://saferskills.ai)</sub>
