# CLAUDE.md — tools/saferskills-admin

Operator CLI over the `X-Admin-Key`-gated `POST/GET /api/v1/admin/*` endpoints
(I-04 Phase C, D-04-28). Mirrors the `tools/data-seed/` layout but is a SEPARATE
uv project with a different audience + safety surface:

| Tool | Audience | Writes to |
|---|---|---|
| `data-seed` | engineers populating fixtures | dev/staging (loopback-exempt seed) |
| `fp-audit` | rubric authors | nothing (read/report) |
| `saferskills-admin` | operators | **production**, via the API (audit-logged) |

## Layout

`cli.py` (root Typer + `@app.callback` building `AdminContext`) → `shared/`
(`context`, `http_client` (X-Admin-Key), `output`, `safety`) → `domains/`
(`sources`, `merge_candidates`, `catalog`, `popularity`, `auth`). Each domain is a
`typer.Typer()` registered via `app.add_typer`.

## Conventions

- **No DB access.** This CLI only calls the API; the backend owns all mutation +
  `admin_audit_log` writes. Never add `psycopg`/SQLAlchemy here.
- **X-Admin-Key only.** The gate header is set in `shared/http_client.create_client`.
  The key comes from `--admin-key` / `SAFERSKILLS_ADMIN_KEY`. **A local API
  (`ENV=development`, no key configured) exempts the gate** — the CLI's default
  `--api-url http://localhost:8000` works with no key (those mutations audit as
  `local-dev`); a key is required only for staging/production targets. Replaced by
  SSO when auth lands (Track E); the CLI keeps working as the transition fallback.
- **Dangerous verbs gate via `shared/safety.require_confirmation`** — `--yes` or
  `SAFERSKILLS_ADMIN_CONFIRM=yes-i-mean-it`. Add a new dangerous verb = add its
  `<domain> <verb>` string to `DANGEROUS_OPS`.
- **No dedicated CI lane** (dev/operator tooling). `ruff` + a `--help` smoke test
  under `tests/`. Run `uv run ruff check .` + `uv run pytest`.

## When you add a command

1. Add the `@app.command()` to the right `domains/<d>/app.py`.
2. Add the matching backend endpoint under `services/api/app/routers/admin.py`
   (X-Admin-Key gated + `admin_audit_log` write).
3. If it mutates production destructively, add it to `DANGEROUS_OPS`.
4. Update this file's command list + `README.md`.
