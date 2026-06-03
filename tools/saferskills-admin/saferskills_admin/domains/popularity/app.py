from __future__ import annotations

import typer

from ...shared.context import get_context
from ...shared.output import invoke
from ...shared.safety import require_confirmation

app = typer.Typer(help="Popularity ranking.", no_args_is_help=True)


@app.command("recompute-now")
def recompute_now(ctx: typer.Context) -> None:
    """Defer an immediate popularity_recompute. Expensive — requires --yes."""
    require_confirmation("popularity recompute-now", get_context(ctx).yes)
    invoke(ctx, "POST", "/api/v1/admin/popularity/recompute-now")


@app.command("top-n")
def top_n(
    ctx: typer.Context,
    n: int = typer.Argument(500, help="How many rows."),
    kind: str = typer.Option("", help="Filter by kind (skill, mcp_server, …)."),
) -> None:
    """List the top-N capabilities by popularity_score."""
    params: dict[str, object] = {"n": n}
    if kind:
        params["kind"] = kind
    invoke(ctx, "GET", "/api/v1/admin/popularity/top-n", params=params)
