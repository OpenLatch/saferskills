from __future__ import annotations

import typer
from rich.console import Console

from ...shared.context import get_context
from ...shared.http_client import create_client

app = typer.Typer(help="Scan operations: list / run individual scans.")
console = Console()


@app.command("list")
def list_scans(
    ctx: typer.Context,
    limit: int = typer.Option(20, help="Max scans to fetch"),
) -> None:
    """GET /api/v1/scans?limit=N — list recent scans."""
    gctx = get_context(ctx)
    with create_client(gctx.api_url, gctx.api_key) as client:
        resp = client.get("/api/v1/scans", params={"limit": limit})
        if resp.status_code == 404:
            console.print("[yellow]/api/v1/scans not shipped yet — comes with Phase B.[/]")
            raise typer.Exit(0)
        resp.raise_for_status()
        scans = resp.json().get("data", [])
    if not scans:
        console.print("[dim]No scans yet.[/]")
        return
    for scan in scans:
        console.print(
            f"  · {scan.get('id', '?'):<14} {scan.get('github_url', '?')} "
            f"→ {scan.get('aggregate_score', '?')} ({scan.get('tier', '?')})"
        )


@app.command("run")
def run(
    ctx: typer.Context,
    github_url: str = typer.Argument(..., help="github.com/<org>/<repo>[/path]"),
) -> None:
    """POST /api/v1/scans — trigger a fresh scan."""
    gctx = get_context(ctx)
    with create_client(gctx.api_url, gctx.api_key) as client:
        resp = client.post("/api/v1/scans", json={"github_url": github_url})
        resp.raise_for_status()
    console.print(f"[bold green]✓[/bold green] {github_url} → {resp.json()}")
