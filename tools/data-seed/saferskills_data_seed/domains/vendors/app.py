from __future__ import annotations

import typer
from rich.console import Console

from ...shared.context import get_context
from ...shared.http_client import create_client

app = typer.Typer(help="Vendor right-of-reply: issue tokens, redeem, seed responses.")
console = Console()


@app.command("verify-issue")
def verify_issue(ctx: typer.Context, slug: str) -> None:
    """POST /api/v1/items/<slug>/vendor/verify/issue — get a one-time token."""
    gctx = get_context(ctx)
    with create_client(gctx.api_url, gctx.api_key) as client:
        resp = client.post(f"/api/v1/items/{slug}/vendor/verify/issue")
        if resp.status_code == 404:
            console.print("[yellow]Vendor verify endpoints are not available on this backend.[/]")
            raise typer.Exit(0)
        resp.raise_for_status()
    console.print(resp.json())


@app.command("verify-redeem")
def verify_redeem(ctx: typer.Context, slug: str, token: str) -> None:
    """POST /api/v1/items/<slug>/vendor/verify/redeem — set the verified cookie."""
    gctx = get_context(ctx)
    with create_client(gctx.api_url, gctx.api_key) as client:
        resp = client.post(
            f"/api/v1/items/{slug}/vendor/verify/redeem",
            json={"token": token},
        )
        if resp.status_code == 404:
            console.print("[yellow]Vendor verify endpoints are not available on this backend.[/]")
            raise typer.Exit(0)
        resp.raise_for_status()
    console.print("[bold green]✓[/bold green] redeemed")


@app.command("seed")
def seed(
    ctx: typer.Context,
    count: int = typer.Option(5, help="Number of vendor responses to seed"),
) -> None:
    """Seed N example vendor responses on the lowest-score catalog items."""
    _ = ctx
    console.print(
        f"[yellow]vendors.seed: scaffolded; the full vendor right-of-reply seeding "
        f"flow is not implemented yet. Would seed {count} responses.[/]"
    )
