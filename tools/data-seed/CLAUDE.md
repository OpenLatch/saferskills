# CLAUDE.md — tools/data-seed/

Standalone uv project. Mirrors `openlatch-platform/tools/data-seed/`. The CLI talks to the SaferSkills API only — never imports from `services/api/`.

## Hard rules

1. **Allowlist is a hard refusal.** `purge run --apply` against any URL not in `PURGE_ALLOWLIST` exits 2. Production URLs are intentionally absent — adding one requires editing `saferskills_data_seed/domains/purge/app.py`.
2. **Rate-limited publish.** `catalog publish` paces at ≤2 scans/sec to stay under the I-02 D-25 rate-limit budget (10/day/IP equivalent). The 50-item seed takes ~25-30s.
3. **No imports from `services/api/`.** The seed tool talks to the API through HTTP only. Sharing Python modules makes the seed brittle to backend refactors.
4. **Fixture corpus is canonical.** `saferskills_data_seed/domains/catalog/files/catalog.yaml` is the demo dataset. ~50 entries spanning all 5 PRD categories with the score distribution from D-FE-14. A1 ships with 8 representative entries; the full 50 lands in a follow-up.

## Architecture

```
saferskills_data_seed/
├── __main__.py          # python -m saferskills_data_seed
├── cli.py               # Typer root + global flags
├── shared/
│   ├── context.py       # GlobalContext dataclass
│   └── http_client.py   # httpx.Client factory
└── domains/
    ├── catalog/         # list / describe / publish
    ├── scans/           # list / run
    ├── vendors/         # verify-issue / verify-redeem / seed
    ├── doctor/          # preflight
    └── purge/           # describe / run (with allowlist + --apply + --yes)
```

Every domain is a `typer.Typer()` subapp registered in `cli.py`. Shared context is attached in the root callback (`attach_context`) and read by subcommands (`get_context`).

## When endpoints don't exist yet

A1 ships before Phase B (scan backend) and Phase C (vendor right-of-reply). Endpoints that don't exist yet return 404. Each subcommand handles 404 explicitly — prints a yellow info message and exits 0 (not an error; the surface just isn't shipped yet). The structure exists so each phase can wire the corresponding endpoint without touching the CLI.

## CI

`.github/workflows/data-seed.yml` runs on every PR touching `tools/data-seed/`:

1. `uv sync`
2. `uv run ruff check .`
3. `uv run ruff format --check .`
4. `uv run saferskills-data-seed --help` (smoke)

Coverage gate isn't enforced — the CLI is dev tooling, not production code.
