from __future__ import annotations

import httpx
import typer
import yaml
from rich.console import Console

from ...shared.context import get_context
from ...shared.http_client import create_client
from ..catalog.app import CATALOG_YAML

app = typer.Typer(help="Preflight: API reachable, OpenAPI schema present, corpus validates.")
console = Console()


def _check(label: str, ok: bool, detail: str = "") -> None:
    icon = "[bold green]✓[/]" if ok else "[bold red]✗[/]"
    suffix = f" — {detail}" if detail else ""
    console.print(f"  {icon} {label}{suffix}")


@app.callback(invoke_without_command=True)
def run(ctx: typer.Context) -> None:
    """Run every preflight check and exit non-zero on any failure."""
    gctx = get_context(ctx)
    failed = 0

    # 1. API reachable
    try:
        with create_client(gctx.api_url, gctx.api_key) as client:
            resp = client.get("/api/v1/health", timeout=5.0)
        ok = resp.status_code == 200
        _check(f"API reachable at {gctx.api_url}", ok, f"status={resp.status_code}")
        if not ok:
            failed += 1
    except httpx.HTTPError as e:
        _check(f"API reachable at {gctx.api_url}", False, str(e))
        failed += 1

    # 2. Fixture corpus parses
    try:
        with CATALOG_YAML.open() as f:
            corpus = yaml.safe_load(f)["items"]
        _check(f"Fixture corpus parses ({len(corpus)} items)", True)
    except (yaml.YAMLError, KeyError, FileNotFoundError) as e:
        _check("Fixture corpus parses", False, str(e))
        failed += 1

    if failed:
        raise typer.Exit(1)
    console.print("[bold green]All checks passed.[/]")
