from __future__ import annotations

import secrets

import typer

app = typer.Typer(help="Admin-key generation.", no_args_is_help=True)


@app.command("gen-admin-key")
def gen_admin_key() -> None:
    """Generate a 32-byte admin key (prefixed opk_admin_). Pipe into the API's
    SAFERSKILLS_ADMIN_KEY Fly secret + your local .env. No API call."""
    typer.echo(f"opk_admin_{secrets.token_hex(32)}")
