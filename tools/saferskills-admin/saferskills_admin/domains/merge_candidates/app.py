from __future__ import annotations

import typer

from ...shared.context import get_context
from ...shared.output import invoke
from ...shared.safety import require_confirmation

app = typer.Typer(help="Fuzzy-dedup merge-candidate review queue.", no_args_is_help=True)


@app.command("list")
def list_candidates(
    ctx: typer.Context,
    status: str = typer.Option("pending", help="pending | merged | rejected"),
    limit: int = typer.Option(20, help="Max rows."),
) -> None:
    """List merge candidates awaiting review."""
    invoke(ctx, "GET", "/api/v1/admin/merge-candidates", params={"status": status, "limit": limit})


@app.command()
def approve(
    ctx: typer.Context,
    candidate_id: str,
    note: str = typer.Option("", help="Decision note."),
) -> None:
    """Approve (merge) a candidate. Dangerous — requires --yes."""
    require_confirmation("merge-candidates approve", get_context(ctx).yes)
    invoke(
        ctx,
        "POST",
        f"/api/v1/admin/merge-candidates/{candidate_id}/decide",
        json={"decision": "merged", "note": note},
    )


@app.command()
def reject(
    ctx: typer.Context,
    candidate_id: str,
    note: str = typer.Option("", help="Decision note."),
) -> None:
    """Reject a candidate. Dangerous — requires --yes."""
    require_confirmation("merge-candidates reject", get_context(ctx).yes)
    invoke(
        ctx,
        "POST",
        f"/api/v1/admin/merge-candidates/{candidate_id}/decide",
        json={"decision": "rejected", "note": note},
    )
