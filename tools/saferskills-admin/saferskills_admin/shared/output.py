from __future__ import annotations

import json as _json
from typing import Any

import typer
from rich.console import Console
from rich.table import Table

from .context import AdminContext, get_context
from .http_client import call

console = Console()


def invoke(ctx: typer.Context, method: str, path: str, **kwargs: Any) -> None:
    """The command body shared by every admin subcommand: resolve context, call
    the API, print the result. Collapses the get_context → call → emit triple."""
    actx = get_context(ctx)
    emit(actx, call(actx, method, path, **kwargs))


def emit(actx: AdminContext, data: Any) -> None:
    """Print a result as JSON (--json) or a pretty table/echo."""
    if actx.json:
        console.print_json(_json.dumps(data, default=str))
        return
    rows = data.get("data") if isinstance(data, dict) else data
    if isinstance(rows, list) and rows and isinstance(rows[0], dict):
        table = Table(show_header=True, header_style="bold")
        cols = list(rows[0].keys())
        for c in cols:
            table.add_column(c)
        for r in rows:
            table.add_row(*[str(r.get(c, "")) for c in cols])
        console.print(table)
    else:
        console.print(data)
