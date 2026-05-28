from __future__ import annotations

from dataclasses import dataclass

import typer


@dataclass(frozen=True)
class GlobalContext:
    """Per-invocation context shared across all commands."""

    api_url: str
    api_key: str | None
    seed: int | None
    json: bool
    verbose: bool
    quiet: bool


def attach_context(ctx: typer.Context, gctx: GlobalContext) -> None:
    """Attach the global context to a Typer Context so subcommands can read it."""
    ctx.obj = gctx


def get_context(ctx: typer.Context) -> GlobalContext:
    """Pull the global context off a Typer Context. Raises if not attached."""
    if not isinstance(ctx.obj, GlobalContext):
        raise RuntimeError(
            "GlobalContext is not attached. The root callback must run before any subcommand."
        )
    return ctx.obj
