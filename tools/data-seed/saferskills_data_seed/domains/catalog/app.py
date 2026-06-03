from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import Any

import typer
import yaml
from rich.console import Console
from rich.progress import Progress

from ...shared.context import get_context
from ...shared.http_client import create_scans_client

app = typer.Typer(help="Catalog seeder: publish ~50 fixture items via the scans API.")
console = Console()

CATALOG_YAML = Path(__file__).parent / "files" / "catalog.yaml"

# Root of the monorepo (two levels up from tools/data-seed/).
_REPO_ROOT = Path(__file__).resolve().parents[5]
_API_ROOT = _REPO_ROOT / "services" / "api"
_INGESTION_SMOKE = _API_ROOT / "scripts" / "ingestion_smoke.py"


def _load_catalog() -> list[dict[str, Any]]:
    with CATALOG_YAML.open() as f:
        return yaml.safe_load(f)["items"]


@app.command("list")
def list_items(ctx: typer.Context) -> None:
    """List the bundled fixture items."""
    _ = ctx
    items = _load_catalog()
    console.print(f"[bold]{len(items)} fixture items:[/bold]")
    for item in items:
        console.print(
            f"  · {item['slug']:<32} score~{item['expected_score']:3d}  "
            f"({item['kind']})  {item['github_url']}"
        )


@app.command("describe")
def describe(ctx: typer.Context, slug: str) -> None:
    """Pretty-print one item's manifest as YAML."""
    _ = ctx
    items = _load_catalog()
    item = next((i for i in items if i["slug"] == slug), None)
    if item is None:
        typer.echo(f"unknown slug: {slug}", err=True)
        raise typer.Exit(1)
    console.print(yaml.dump(item, sort_keys=False))


@app.command("seed-demo")
def seed_demo(
    ctx: typer.Context,
    rate: float = typer.Option(2.0, help="Scans per second cap (≤2.0 per I-02 rate-limit)"),
    dry_run: bool = typer.Option(False, "--dry-run"),
) -> None:
    """POST /api/v1/scans for each fixture item. Idempotency-key dedup; re-runs are safe."""
    gctx = get_context(ctx)
    items = _load_catalog()
    if dry_run:
        console.print(f"[dim]DRY RUN: would publish {len(items)} items at {rate} scans/s[/dim]")
        return

    pace_s = max(1.0 / max(rate, 0.1), 0.5)
    client = create_scans_client(gctx.api_url, gctx.api_key)
    successes = 0
    failures: list[tuple[str, str]] = []
    with client, Progress() as p:
        task = p.add_task("[teal]Publishing...[/]", total=len(items))
        for item in items:
            try:
                resp = client.post("/api/v1/scans", json={"github_url": item["github_url"]})
                resp.raise_for_status()
                successes += 1
            except Exception as e:  # noqa: BLE001 — surface upstream error verbatim
                failures.append((item["slug"], str(e)))
            time.sleep(pace_s)
            p.advance(task)
    console.print(f"[bold green]✓[/bold green] {successes} published / {len(failures)} failed")
    for slug, err in failures:
        console.print(f"  ! {slug}: {err}")


@app.command("publish", hidden=True)
def publish(
    ctx: typer.Context,
    rate: float = typer.Option(2.0, help="Scans per second cap (≤2.0 per I-02 rate-limit)"),
    dry_run: bool = typer.Option(False, "--dry-run"),
) -> None:
    """Deprecated alias for seed-demo. Use `catalog seed-demo` instead."""
    console.print(
        "[yellow]WARNING:[/yellow] `catalog publish` is deprecated. "
        "Use `catalog seed-demo` instead."
    )
    seed_demo(ctx, rate=rate, dry_run=dry_run)


@app.command("ingest-stub")
def ingest_stub(
    ctx: typer.Context,
    source: str = typer.Argument(
        "github_topics",
        help="Source name to run the stub cycle for (default: github_topics).",
    ),
    database_url: str = typer.Option(
        "postgresql+asyncpg://postgres:dev@localhost:5432/saferskills_dev",
        envvar="DATABASE_URL",
        help="PostgreSQL connection string.",
    ),
) -> None:
    """Run ONE offline StubAdapter cycle against the API database.

    Drives `services/api/scripts/ingestion_smoke.py` via uv so no imports
    from services/api/ are needed in this package (cf. tools/data-seed/CLAUDE.md
    hard rule #3).

    Does NOT hit the network — StubAdapter uses canned repo-JSON dicts declared
    in `ingestion_smoke.py`. Requires the API database to be reachable at
    DATABASE_URL (migrate it first with `alembic upgrade head`).

    Limitation: the `source` argument is accepted for UI consistency but
    StubAdapter always uses the github_topics normaliser shape regardless of
    source name.
    """
    _ = ctx

    if not _INGESTION_SMOKE.exists():
        console.print(
            f"[red]ERROR:[/red] ingestion_smoke.py not found at {_INGESTION_SMOKE}\n"
            "Is the monorepo layout intact?"
        )
        raise typer.Exit(2)

    console.print(
        f"[dim]Running ingestion stub cycle for source '{source}' "
        f"via {_API_ROOT.relative_to(_REPO_ROOT)}...[/dim]"
    )

    result = subprocess.run(
        [
            "uv",
            "run",
            "--project",
            str(_API_ROOT),
            "python",
            str(_INGESTION_SMOKE),
        ],
        env={
            **__import__("os").environ,
            "DATABASE_URL": database_url,
            "INGESTION_WORKER_ENABLED": "false",
        },
        text=True,
        capture_output=False,
    )

    if result.returncode != 0:
        console.print(f"[red]FAIL:[/red] ingestion smoke exited {result.returncode}")
        raise typer.Exit(result.returncode)

    console.print("[bold green]✓[/bold green] ingest-stub cycle completed.")
