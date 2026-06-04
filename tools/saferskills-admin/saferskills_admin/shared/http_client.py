from __future__ import annotations

import re
from typing import Any

import httpx
import typer

from .context import AdminContext


def _prefer_ipv4_localhost(api_url: str) -> str:
    """Rewrite a `localhost` host to 127.0.0.1.

    On Windows `localhost` resolves to IPv6 `::1` first; uvicorn binds IPv4 only
    by default, so httpx stalls ~2s on the dead IPv6 attempt before falling back
    on every request — the dashboard then feels frozen / never-refreshing. The
    rewrite is host-exact (`localhost` token only), so any real remote URL is
    untouched.
    """
    return re.sub(r"^(https?://)localhost(?=[:/]|$)", r"\g<1>127.0.0.1", api_url, count=1)


def create_client(api_url: str, admin_key: str | None) -> httpx.Client:
    """Sync httpx client carrying the X-Admin-Key gate header."""
    headers: dict[str, str] = {
        "User-Agent": "saferskills-admin/0.1.0",
        "Accept": "application/json",
    }
    if admin_key:
        headers["X-Admin-Key"] = admin_key
    return httpx.Client(
        base_url=_prefer_ipv4_localhost(api_url).rstrip("/"),
        headers=headers,
        timeout=httpx.Timeout(connect=5.0, read=60.0, write=10.0, pool=5.0),
        follow_redirects=False,
    )


def call(
    actx: AdminContext,
    method: str,
    path: str,
    *,
    json: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
) -> Any:
    """Issue one admin API call; raise typer.Exit(1) on transport/HTTP error."""
    try:
        with create_client(actx.api_url, actx.admin_key) as client:
            resp = client.request(method, path, json=json, params=params)
    except httpx.HTTPError as exc:
        typer.secho(f"request failed: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(1) from exc
    if resp.status_code >= 400:
        detail = ""
        try:
            detail = resp.json().get("detail", resp.text)
        except ValueError:
            detail = resp.text
        typer.secho(f"HTTP {resp.status_code}: {detail}", fg=typer.colors.RED, err=True)
        raise typer.Exit(1)
    if resp.status_code == 204 or not resp.content:
        return {}
    return resp.json()
