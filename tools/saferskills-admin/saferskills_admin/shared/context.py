from __future__ import annotations

from dataclasses import dataclass

import typer


@dataclass(frozen=True)
class AdminContext:
    """Per-invocation context shared across all admin subcommands."""

    api_url: str
    admin_key: str | None
    json: bool
    verbose: bool
    quiet: bool
    yes: bool


def attach_context(ctx: typer.Context, actx: AdminContext) -> None:
    ctx.obj = actx


def get_context(ctx: typer.Context) -> AdminContext:
    if not isinstance(ctx.obj, AdminContext):
        raise RuntimeError(
            "AdminContext is not attached. The root callback must run before any subcommand."
        )
    return ctx.obj
