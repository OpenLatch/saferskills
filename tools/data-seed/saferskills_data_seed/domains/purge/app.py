from __future__ import annotations

import os
import time

import typer
from rich.console import Console

from ...shared.context import get_context
from ...shared.http_client import create_client

app = typer.Typer(help="Purge SaferSkills DB state. **Local / staging only.**")
console = Console()

# Allow-listed base URLs. Production URLs are intentionally absent. Adding one
# requires editing this file AND filing a PR review.
PURGE_ALLOWLIST: frozenset[str] = frozenset(
    {
        "http://localhost:8000",
        "http://api:8000",  # docker-compose service name
        "https://staging.saferskills.ai",
    }
)


@app.command("describe")
def describe(ctx: typer.Context) -> None:
    """Print what `purge run --apply` would delete on the current target."""
    gctx = get_context(ctx)
    console.print(f"[bold]Target:[/bold] {gctx.api_url}")
    if gctx.api_url not in PURGE_ALLOWLIST:
        console.print(
            f"[bold red]REFUSED:[/] {gctx.api_url} is not on the allowlist. "
            "Purge is restricted to local + staging.",
        )
        raise typer.Exit(2)
    console.print("Would DELETE: catalog_items, scans, findings, vendor_responses")


@app.command("run")
def run(
    ctx: typer.Context,
    apply: bool = typer.Option(False, "--apply", help="Actually delete. Default = dry-run."),
    yes: bool = typer.Option(False, "--yes", help="Skip the interactive confirmation."),
) -> None:
    """Reset the database to a clean state. Local / staging only."""
    gctx = get_context(ctx)

    if gctx.api_url not in PURGE_ALLOWLIST:
        console.print(
            f"[bold red]ERROR:[/] purge is restricted to local / staging. Got: {gctx.api_url}",
        )
        raise typer.Exit(2)

    if not apply:
        console.print("[dim]DRY RUN — pass --apply to actually delete.[/]")
        return

    env_confirm = os.environ.get("SAFERSKILLS_DATA_SEED_CONFIRM")
    if not yes and env_confirm != "yes-i-mean-it":
        console.print(
            "[bold red]Refusing to purge without confirmation.[/] "
            "Pass --yes, or set SAFERSKILLS_DATA_SEED_CONFIRM=yes-i-mean-it.",
        )
        raise typer.Exit(2)

    console.print(f"[bold yellow]About to DELETE on {gctx.api_url}.[/] Ctrl+C in 3s to abort.")
    time.sleep(3)

    with create_client(gctx.api_url, gctx.api_key) as client:
        for path in (
            "/api/v1/admin/scans",
            "/api/v1/admin/catalog_items",
            "/api/v1/admin/vendor_responses",
        ):
            resp = client.delete(path)
            if resp.status_code == 404:
                console.print(f"[dim]{path} not implemented yet — skipping[/]")
                continue
            resp.raise_for_status()
            console.print(f"  ✓ {path} → {resp.status_code}")

    console.print("[bold green]Purge complete.[/]")
