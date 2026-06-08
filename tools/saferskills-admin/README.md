# saferskills-admin

Operator CLI for SaferSkills production (I-04 Phase C, D-04-28). A thin Typer
client over the `X-Admin-Key`-gated `POST/GET /api/v1/admin/*` endpoints. Distinct
from `tools/data-seed/` (dev fixtures) and `tools/fp-audit/` (rubric FP audit) —
this one mutates **production** via the API, so every mutation is audit-logged
server-side and dangerous verbs require confirmation.

## Auth

Every command sends the `X-Admin-Key` header. Provide it via `--admin-key` or the
`SAFERSKILLS_ADMIN_KEY` env var. Generate one with:

```bash
uv run saferskills-admin auth gen-admin-key
# → opk_admin_a9b3…  (set as the API's SAFERSKILLS_ADMIN_KEY Fly secret + your .env)
```

**Local development needs no key.** A local API running with the default
`ENV=development` and no `SAFERSKILLS_ADMIN_KEY` configured exempts the admin gate,
so `uv run saferskills-admin sources list` (default `--api-url http://localhost:8000`)
works out of the box — those mutations audit as `local-dev`. A key is only required
when targeting **staging/production** (their `ENV` is set, so the gate stays
mandatory). Set one there as an `X-Admin-Key` / `SAFERSKILLS_ADMIN_KEY` value.

## Usage

```bash
# point at an environment (default http://localhost:8000)
export SAFERSKILLS_ADMIN_KEY=opk_admin_…
uv run saferskills-admin --api-url https://saferskills-api-staging.fly.dev sources list

# sources
uv run saferskills-admin sources list
uv run saferskills-admin sources status mcp_so
uv run saferskills-admin sources runs npm --limit 50          # ingestion-run history (scriptable)
uv run saferskills-admin sources dashboard                    # eagle-eye TUI (interactive)
uv run saferskills-admin sources pause mcp_so --reason "operator-request" --contact abuse@mcp.so
uv run saferskills-admin sources unpause mcp_so
uv run saferskills-admin sources force-cycle npm

# merge candidates (approve/reject are dangerous → --yes)
uv run saferskills-admin merge-candidates list --status pending --limit 20
uv run saferskills-admin merge-candidates approve <id> --note "same project" --yes

# catalog (archive/un-archive are dangerous → --yes)
uv run saferskills-admin catalog re-classify acme--github-mcp
uv run saferskills-admin catalog inspect-events acme--github-mcp --limit 50
uv run saferskills-admin catalog archive dead--repo --reason "spam" --yes

# popularity (recompute-now is expensive → --yes)
uv run saferskills-admin popularity recompute-now --yes
uv run saferskills-admin popularity top-n 500 --kind mcp_server
```

`--json` emits CI-parseable output. Dangerous mutations require `--yes` or
`SAFERSKILLS_ADMIN_CONFIRM=yes-i-mean-it`.

## Dashboard TUI (`sources dashboard`)

`sources dashboard` launches an interactive [Textual](https://textual.textualize.io/)
"eagle-eye" view over `GET /admin/sources` + `…/{source}/runs`:

- **Overview** — overall-status chip + counts, a `critical[]` banner, and a table of
  every source (status · last run · added/updated · next run · fails). Auto-refreshes
  every 5s. `↑/↓` select, `Enter` drills in, `r` refresh, `f` cycles the
  all/critical/running filter, `c` force-cycles **all** sources (behind a confirm modal;
  the inline status reports the acknowledged/failed tally so a partial failure never
  hides the successes), `q` quits. A connection error shows a red bar and keeps the last
  good snapshot.
- **Drill-down** — live/last-run/schedule/health cards + run history. `Esc`/`backspace`
  goes back; `c` force-cycle, `p` pause, `u` unpause — each behind a confirm modal, then
  the same audit-logged admin endpoint + refresh.

Terminal-only (no browser). Needs the `textual` dependency (installed via `uv sync`).
