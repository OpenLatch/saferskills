from __future__ import annotations

import os

import typer

CONFIRM_ENV = "SAFERSKILLS_ADMIN_CONFIRM"

# Dangerous / expensive mutations that require --yes or the confirm env var.
DANGEROUS_OPS: frozenset[str] = frozenset(
    {
        "merge-candidates approve",
        "merge-candidates reject",
        "catalog archive",
        "catalog un-archive",
        "sources disable",
        "popularity recompute-now",  # not destructive, but expensive — confirm
    }
)


def require_confirmation(op_name: str, yes: bool) -> None:
    """Gate a dangerous op behind --yes or SAFERSKILLS_ADMIN_CONFIRM=yes-i-mean-it."""
    if op_name not in DANGEROUS_OPS:
        return
    if yes:
        return
    if os.environ.get(CONFIRM_ENV) == "yes-i-mean-it":
        return
    typer.secho(
        f"Operation `{op_name}` is dangerous; pass --yes or set {CONFIRM_ENV}=yes-i-mean-it.",
        fg=typer.colors.YELLOW,
        err=True,
    )
    raise typer.Exit(2)
