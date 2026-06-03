from __future__ import annotations

import os
import time
from urllib.parse import urlsplit, urlunsplit

import psycopg
import typer
from rich.console import Console

console = Console()
app = typer.Typer(help="Purge SaferSkills DB state. **Local only.**")

# Default dev DSN — mirrors `services/api/app/core/config.py::Settings.database_url`
# (sans the `+asyncpg` driver suffix, which psycopg doesn't understand). The
# operator can override with `--database-url` or the `DATABASE_URL` env var.
DEFAULT_DSN = "postgresql://postgres:dev@localhost:5432/saferskills_dev"

# Hosts a purge may target. Loopback only — a laptop can't (and must not) reach
# the Fly-internal staging/prod DB, so there is intentionally no remote entry.
# The old API-URL allowlist was moot: SaferSkills has no admin bulk-delete
# endpoint by design (deletion is vendor-appeals / operator-runbook only, see
# `security.md`), so a purge can only run as a direct DB operation.
HOST_ALLOWLIST: frozenset[str] = frozenset({"localhost", "127.0.0.1", "::1"})

# The one table a purge must never touch — it pins the Alembic schema version,
# so truncating it would strand the DB at "no migrations applied" while the
# schema is actually at head. Every other public table is discovered at runtime
# (no hardcoded list to drift against the schema — the bug this rewrite fixes).
PROTECTED_TABLES: frozenset[str] = frozenset({"alembic_version"})


def _normalize_dsn(raw: str) -> str:
    """Strip a SQLAlchemy `+driver` suffix and the legacy `postgres://` alias so
    the DSN is a plain libpq URL psycopg accepts."""
    parts = urlsplit(raw)
    scheme = parts.scheme.split("+", 1)[0]
    if scheme == "postgres":
        scheme = "postgresql"
    return urlunsplit((scheme, parts.netloc, parts.path, parts.query, parts.fragment))


def _resolve_dsn(database_url: str | None) -> str:
    return _normalize_dsn(database_url or os.environ.get("DATABASE_URL") or DEFAULT_DSN)


def _guard_host(dsn: str) -> str:
    """Refuse any non-loopback target. Returns the host for display."""
    host = urlsplit(dsn).hostname or ""
    if host not in HOST_ALLOWLIST:
        console.print(
            f"[bold red]REFUSED:[/] DB host {host!r} is not loopback. "
            f"Purge is restricted to {sorted(HOST_ALLOWLIST)}.",
        )
        raise typer.Exit(2)
    return host


def _purgeable_tables(conn: psycopg.Connection) -> list[str]:
    """Every public base table except the protected set, alphabetical."""
    rows = conn.execute(
        "SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename"
    ).fetchall()
    return [t for (t,) in rows if t not in PROTECTED_TABLES]


def _row_counts(conn: psycopg.Connection, tables: list[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for t in tables:
        # Table names come from pg_tables, not user input — safe to interpolate.
        counts[t] = conn.execute(f'SELECT count(*) FROM "{t}"').fetchone()[0]  # type: ignore[index]
    return counts


@app.command("describe")
def describe(
    ctx: typer.Context,
    database_url: str = typer.Option(None, "--database-url", help="libpq DSN (defaults to dev)."),
) -> None:
    """Show what `purge run --apply` would TRUNCATE on the current target."""
    _ = ctx
    dsn = _resolve_dsn(database_url)
    host = _guard_host(dsn)
    console.print(f"[bold]Target DB:[/bold] {host} ({urlsplit(dsn).path.lstrip('/')})")
    with psycopg.connect(dsn, connect_timeout=5) as conn:
        tables = _purgeable_tables(conn)
        counts = _row_counts(conn, tables)
    total = sum(counts.values())
    console.print(f"Would TRUNCATE {len(tables)} tables ({total} rows) — keeping alembic_version:")
    for t in tables:
        console.print(f"  · {t:<24} {counts[t]:>8} rows")


@app.command("run")
def run(
    ctx: typer.Context,
    apply: bool = typer.Option(False, "--apply", help="Actually delete. Default = dry-run."),
    yes: bool = typer.Option(False, "--yes", help="Skip the interactive confirmation."),
    database_url: str = typer.Option(None, "--database-url", help="libpq DSN (defaults to dev)."),
) -> None:
    """Reset the database to a clean, schema-at-head state. Loopback only.

    TRUNCATEs every public table except `alembic_version` (RESTART IDENTITY
    CASCADE), so the schema stays migrated while all rows — catalog_items,
    scans, scan_runs, findings, scan_events, upload_files, artifact_blobs,
    item_sources, vendor_*, rate_limits — are cleared atomically, with no FK
    orphans left behind.
    """
    _ = ctx
    dsn = _resolve_dsn(database_url)
    host = _guard_host(dsn)

    if not apply:
        console.print("[dim]DRY RUN — pass --apply to actually delete.[/]")
        console.print("[dim]Run `purge describe` to see the target + row counts.[/]")
        return

    env_confirm = os.environ.get("SAFERSKILLS_DATA_SEED_CONFIRM")
    if not yes and env_confirm != "yes-i-mean-it":
        console.print(
            "[bold red]Refusing to purge without confirmation.[/] "
            "Pass --yes, or set SAFERSKILLS_DATA_SEED_CONFIRM=yes-i-mean-it.",
        )
        raise typer.Exit(2)

    console.print(f"[bold yellow]About to TRUNCATE all rows on {host}.[/] Ctrl+C in 3s to abort.")
    time.sleep(3)

    with psycopg.connect(dsn, connect_timeout=5) as conn:
        tables = _purgeable_tables(conn)
        if not tables:
            console.print("[yellow]No purgeable tables found — nothing to do.[/]")
            return
        before = sum(_row_counts(conn, tables).values())
        quoted = ", ".join(f'"{t}"' for t in tables)
        conn.execute(f"TRUNCATE {quoted} RESTART IDENTITY CASCADE")
        conn.commit()

    console.print(
        f"[bold green]Purge complete.[/] Truncated {len(tables)} tables "
        f"({before} rows cleared); alembic_version preserved."
    )
