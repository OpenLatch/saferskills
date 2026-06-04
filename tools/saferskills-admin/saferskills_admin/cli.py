from __future__ import annotations

import contextlib
import sys

import typer

from .domains.auth.app import app as auth_app
from .domains.catalog.app import app as catalog_app
from .domains.merge_candidates.app import app as merge_candidates_app
from .domains.popularity.app import app as popularity_app
from .domains.sources.app import app as sources_app
from .shared.context import AdminContext, attach_context

# UTF-8 stdio so Rich glyphs don't crash a legacy Windows console.
for _stream in (sys.stdout, sys.stderr):
    with contextlib.suppress(AttributeError, ValueError):
        _stream.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

app = typer.Typer(
    name="saferskills-admin",
    help="SaferSkills operator CLI — sources, merge-candidates, catalog, popularity, auth.",
    no_args_is_help=True,
)


@app.callback()
def root(
    ctx: typer.Context,
    api_url: str = typer.Option(
        # 127.0.0.1, not `localhost`, to dodge the Windows IPv6 stall — an
        # operator-supplied `localhost` is still rewritten in http_client.py
        # (_prefer_ipv4_localhost), which is the canonical chokepoint.
        "http://127.0.0.1:8000",
        envvar="SAFERSKILLS_API_URL",
        help="API base URL (use 127.0.0.1 not localhost to avoid IPv6 stalls)",
    ),
    admin_key: str | None = typer.Option(
        None,
        envvar="SAFERSKILLS_ADMIN_KEY",
        help="Admin key sent as the X-Admin-Key header.",
    ),
    json_out: bool = typer.Option(False, "--json", help="CI-parseable JSON output"),
    verbose: bool = typer.Option(False, "--verbose"),
    quiet: bool = typer.Option(False, "--quiet"),
    yes: bool = typer.Option(False, "--yes", help="Confirm dangerous mutations."),
) -> None:
    """Set per-invocation context shared by every subcommand."""
    attach_context(
        ctx,
        AdminContext(
            api_url=api_url,
            admin_key=admin_key,
            json=json_out,
            verbose=verbose,
            quiet=quiet,
            yes=yes,
        ),
    )


app.add_typer(sources_app, name="sources")
app.add_typer(merge_candidates_app, name="merge-candidates")
app.add_typer(catalog_app, name="catalog")
app.add_typer(popularity_app, name="popularity")
app.add_typer(auth_app, name="auth")


if __name__ == "__main__":
    app()
