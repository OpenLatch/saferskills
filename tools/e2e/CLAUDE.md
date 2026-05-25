# CLAUDE.md — tools/e2e/

End-to-end test orchestrator for the SaferSkills platform. Mirrors the
`openlatch-platform/tools/e2e/` architecture, with a strict-async,
Pydantic-typed twist.

## Architecture

One command = one file under `saferskills_e2e/commands/`. Every command
extends `BaseCommand` (abstract `name`, `description`, `async run(config)
-> ExitCode`). Shared helpers live under `saferskills_e2e/shared/` and
are imported explicitly — no star imports, no metaclass magic.

```
saferskills_e2e/
├── cli.py                 # argparse + Config.from_args + dispatcher
├── __main__.py            # `python -m saferskills_e2e`
├── commands/
│   ├── base.py            # BaseCommand ABC
│   ├── doctor.py          # API + base-URL reachability
│   ├── smoke.py           # /api/v1/health + /openapi.json contracts
│   ├── homepage.py        # Playwright: wordmark + email capture form
│   └── all.py             # Sequential dispatcher, stops on first failure
└── shared/
    ├── exit_codes.py      # IntEnum: OK, FAIL_REACHABILITY, FAIL_HEALTH, …
    ├── config.py          # Pydantic Config (env + CLI args overlay)
    ├── output.py          # Rich-backed print helpers (single chokepoint)
    ├── http_client.py     # make_client(config) -> httpx.AsyncClient
    ├── fixtures.py        # JSON shape assertions
    └── timing.py          # @async_timed + Stopwatch
```

## Standards

- **Python 3.14+**, managed with `uv` (`uv sync`, `uv run`).
- **Strict typing**: `pyright --strict` clean. No `Any` leaks, no
  implicit `None` returns.
- **Async I/O only**: `httpx.AsyncClient` + `playwright.async_api`.
  No `requests`, no `selenium`.
- **No bare `print()`**: every command writes through `shared/output.py`
  (`print_header`, `print_ok`, `print_warn`, `print_fail`, `print_table`).
  Rich handles colour/TTY detection; the orchestrator is the only thing
  that decides what gets shown.
- Exit codes: `OK=0`, `FAIL_*` per failure mode, `FAIL_CONFIG=20`,
  `FAIL_UNKNOWN=99`. See `shared/exit_codes.py`.

## Adding a new command

1. Create `commands/<name>.py` with a `class <Name>Command(BaseCommand)`.
2. Implement `name`, `description`, and `async run(config) -> ExitCode`.
3. Register it in `commands/__init__.py` `ALL_COMMANDS`.
4. If it should be part of `all`, append to `COMMAND_SEQUENCE` (also
   in `commands/__init__.py`).
5. Add a row to the README `Commands` table.

## Playwright first-run

`playwright install chromium` is a manual step (documented in the
README). The `homepage` and `all` commands surface a `BrowserType.launch:
Executable doesn't exist` error if the browser binary is missing — that
error message is left intact so the operator sees the install hint
verbatim. No silent fallback, no auto-install.
