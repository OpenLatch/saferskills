from __future__ import annotations

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


@app.command("publish")
def publish(
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
