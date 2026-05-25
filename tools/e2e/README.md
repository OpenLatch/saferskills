# saferskills-e2e

End-to-end test orchestrator for the SaferSkills platform. A small async
Python CLI that validates service reachability, HTTP contracts, and the
public marketing homepage against a running stack (local Docker, staging,
or production).

## Setup

```bash
cd tools/e2e
uv sync
uv run playwright install chromium
```

The first `playwright install chromium` downloads a versioned headless
Chromium into Playwright's cache (`~/.cache/ms-playwright` on Linux/macOS,
`%LOCALAPPDATA%\ms-playwright` on Windows). Re-running is a no-op once the
binary is present. CI runs this step explicitly before invoking the
suite; locally the `homepage` and `all` commands surface a clear error
if the browser is missing.

## Commands

| Command    | What it checks                                                                 | Auth |
|------------|--------------------------------------------------------------------------------|------|
| `doctor`   | API + base-URL reachability, per-target latency.                               | None |
| `smoke`    | `GET /api/v1/health` returns `{"status":"ok"}` and `/openapi.json` is parseable. | None |
| `homepage` | Playwright loads `<base_url>`, asserts wordmark + email capture, screenshots.  | None |
| `all`      | Runs `doctor → smoke → homepage` in order, stops on first failure.             | None |

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
```

## Environment

| Variable                | Default                  | Purpose                                                         |
|-------------------------|--------------------------|-----------------------------------------------------------------|
| `SAFERSKILLS_API_URL`   | `http://localhost:8000`  | FastAPI backend root URL.                                       |
| `SAFERSKILLS_BASE_URL`  | `http://localhost:5173`  | Public marketing site root URL.                                 |

CLI flags `--api-url` / `--base-url` override the env vars when both
are present. Screenshots are written under
`<repo_root>/.local/screenshots/`.

## Exit codes

| Code | Meaning                          |
|------|----------------------------------|
| `0`  | All assertions passed.           |
| `10` | A target was not reachable.      |
| `11` | `/api/v1/health` regressed.      |
| `12` | `/openapi.json` regressed.       |
| `13` | Homepage assertions regressed.   |
| `20` | Bad config (missing URL, etc.).  |
| `99` | Unhandled error.                 |

`all` propagates the exit code of the first failing sub-command.
