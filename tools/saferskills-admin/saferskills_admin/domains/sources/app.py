from __future__ import annotations

import typer

from ...shared.context import get_context
from ...shared.http_client import call
from ...shared.output import emit, invoke

app = typer.Typer(help="Ingestion source control.", no_args_is_help=True)


@app.command("list")
def list_sources(ctx: typer.Context) -> None:
    """List all 14 sources with status + last cycle time."""
    invoke(ctx, "GET", "/api/v1/admin/sources")


@app.command()
def status(ctx: typer.Context, source: str) -> None:
    """Show one source's status row."""
    actx = get_context(ctx)
    data = call(actx, "GET", "/api/v1/admin/sources")
    rows = [r for r in data.get("data", []) if r.get("source") == source]
    if not rows:
        typer.secho(f"unknown source {source!r}", fg=typer.colors.RED, err=True)
        raise typer.Exit(1)
    emit(actx, {"data": rows})


@app.command()
def pause(
    ctx: typer.Context,
    source: str,
    reason: str = typer.Option("", help="Why the source is paused."),
    contact: str = typer.Option("", help="Operator contact email."),
) -> None:
    """Pause one source (operator-request workflow)."""
    invoke(
        ctx,
        "POST",
        f"/api/v1/admin/sources/{source}/pause",
        json={"reason": reason, "contact": contact},
    )


@app.command()
def unpause(ctx: typer.Context, source: str) -> None:
    """Re-activate a paused source."""
    invoke(ctx, "POST", f"/api/v1/admin/sources/{source}/unpause")


@app.command("force-cycle")
def force_cycle(ctx: typer.Context, source: str) -> None:
    """Defer one immediate adapter cycle (after a parser fix lands)."""
    invoke(ctx, "POST", f"/api/v1/admin/sources/{source}/force-cycle")
