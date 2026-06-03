from __future__ import annotations

import typer

from ...shared.context import get_context
from ...shared.output import invoke
from ...shared.safety import require_confirmation

app = typer.Typer(help="Catalog item operations.", no_args_is_help=True)


@app.command("re-classify")
def re_classify(ctx: typer.Context, slug: str) -> None:
    """Re-run kind + quality_tier + agent_compatibility heuristics for one item."""
    invoke(ctx, "POST", f"/api/v1/admin/catalog/{slug}/re-classify")


@app.command("inspect-events")
def inspect_events(
    ctx: typer.Context,
    slug: str,
    limit: int = typer.Option(50, help="Max events."),
) -> None:
    """Show recent ingestion_events referencing this item."""
    invoke(ctx, "GET", f"/api/v1/admin/catalog/{slug}/events", params={"limit": limit})


@app.command()
def archive(
    ctx: typer.Context,
    slug: str,
    reason: str = typer.Option("", help="Archive reason."),
) -> None:
    """Force-archive an item. Dangerous — requires --yes."""
    require_confirmation("catalog archive", get_context(ctx).yes)
    invoke(ctx, "POST", f"/api/v1/admin/catalog/{slug}/archive", json={"reason": reason})


@app.command("un-archive")
def un_archive(ctx: typer.Context, slug: str) -> None:
    """Restore an archived item. Dangerous — requires --yes."""
    require_confirmation("catalog un-archive", get_context(ctx).yes)
    invoke(ctx, "POST", f"/api/v1/admin/catalog/{slug}/un-archive")
