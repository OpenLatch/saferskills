from __future__ import annotations

import typer

from .domains.catalog.app import app as catalog_app
from .domains.doctor.app import app as doctor_app
from .domains.purge.app import app as purge_app
from .domains.scans.app import app as scans_app
from .domains.vendors.app import app as vendors_app
from .shared.context import GlobalContext, attach_context

app = typer.Typer(
    name="saferskills-data-seed",
    help="SaferSkills dev tool: seed catalog + scans + vendor responses; purge org state.",
    no_args_is_help=True,
)


@app.callback()
def root(
    ctx: typer.Context,
    api_url: str = typer.Option("http://localhost:8000", help="API base URL"),
    api_key: str | None = typer.Option(
        None,
        envvar="SAFERSKILLS_API_KEY",
        help="Bearer token (lands with auth in W5)",
    ),
    seed: int | None = typer.Option(None, help="Make runs reproducible"),
    json_out: bool = typer.Option(False, "--json", help="CI-parseable output"),
    verbose: bool = typer.Option(False, "--verbose"),
    quiet: bool = typer.Option(False, "--quiet"),
) -> None:
    """Set per-invocation context shared by every subcommand."""
    attach_context(
        ctx,
        GlobalContext(
            api_url=api_url,
            api_key=api_key,
            seed=seed,
            json=json_out,
            verbose=verbose,
            quiet=quiet,
        ),
    )


app.add_typer(catalog_app, name="catalog")
app.add_typer(scans_app, name="scans")
app.add_typer(vendors_app, name="vendors")
app.add_typer(doctor_app, name="doctor")
app.add_typer(purge_app, name="purge")


if __name__ == "__main__":
    app()
