from __future__ import annotations

from typing import Any

import typer

from ...shared.context import get_context
from ...shared.http_client import call
from ...shared.output import emit, invoke

app = typer.Typer(help="Ingestion source control.", no_args_is_help=True)


def _project(p: dict[str, Any]) -> dict[str, Any]:
    """Flatten one enriched eagle-eye provider into table-friendly columns.

    The `GET /admin/sources` payload now nests `health` / `last_run` / `schedule`;
    the rich-table renderer wants flat scalar cells, so project a readable subset.
    """
    h = p.get("health") or {}
    lr = p.get("last_run") or {}
    sched = p.get("schedule") or {}
    return {
        "source": p.get("source"),
        "status": h.get("status", p.get("status")),
        "cursor": p.get("status"),
        "enabled": p.get("enabled"),
        "last_run": lr.get("started_at"),
        "added": lr.get("items_added"),
        "updated": lr.get("items_updated"),
        "fails": p.get("consecutive_failure_count"),
        "next_run": (sched.get("next_expected_run")),
    }


@app.command("list")
def list_sources(ctx: typer.Context) -> None:
    """List all sources with derived health + last-cycle summary."""
    actx = get_context(ctx)
    data = call(actx, "GET", "/api/v1/admin/sources")
    if actx.json:
        emit(actx, data)  # full eagle-eye snapshot for scripting
        return
    emit(actx, {"data": [_project(p) for p in data.get("data", [])]})


@app.command()
def status(ctx: typer.Context, source: str) -> None:
    """Show one source's status row (flat projection; --json gives full detail)."""
    actx = get_context(ctx)
    data = call(actx, "GET", "/api/v1/admin/sources")
    rows = [r for r in data.get("data", []) if r.get("source") == source]
    if not rows:
        typer.secho(f"unknown source {source!r}", fg=typer.colors.RED, err=True)
        raise typer.Exit(1)
    if actx.json:
        emit(actx, {"data": rows})
        return
    emit(actx, {"data": [_project(rows[0])]})


@app.command()
def runs(
    ctx: typer.Context,
    source: str,
    limit: int = typer.Option(50, help="Page size (max 200)."),
    before: str = typer.Option("", help="Keyset cursor — ISO timestamp; runs before it."),
) -> None:
    """Scriptable ingestion-run history for one source (started_at DESC)."""
    actx = get_context(ctx)
    params: dict[str, Any] = {"limit": limit}
    if before:
        params["before"] = before
    emit(actx, call(actx, "GET", f"/api/v1/admin/sources/{source}/runs", params=params))


@app.command()
def dashboard(ctx: typer.Context) -> None:
    """Launch the eagle-eye ingestion dashboard (Textual TUI)."""
    actx = get_context(ctx)
    from .tui.app import SourcesDashboardApp
    from .tui.client import SourcesHealthClient

    SourcesDashboardApp(SourcesHealthClient(actx)).run()


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
