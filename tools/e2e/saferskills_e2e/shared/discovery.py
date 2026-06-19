"""Catalog/scan discovery helpers for the smoke commands.

The item-detail / vendor-respond / badge / og commands all need to find a real
slug or scan from the running API (the catalog can be empty until data-seed
runs, so callers skip gracefully on `None`). Centralised here so the four
commands share one `make_client`-based fetch instead of re-rolling httpx.
"""

from __future__ import annotations

from typing import Any

from saferskills_e2e.shared.config import Config
from saferskills_e2e.shared.http_client import make_client


async def discover_first_item_slug(config: Config) -> str | None:
    """Slug of the first catalog item, or None when the catalog is empty."""
    async with make_client(config) as client:
        resp = await client.get(f"{config.api_url}/api/v1/items", params={"limit": 1})
    resp.raise_for_status()
    data = resp.json().get("data", [])
    return data[0]["slug"] if data else None


async def discover_first_upload_item(config: Config) -> str | None:
    """Slug of the first PUBLIC upload-sourced catalog item, or None.

    Uses the `artifact_source=upload` filter — empty on a fresh staging until an
    upload is published, so callers skip gracefully on `None`."""
    async with make_client(config) as client:
        resp = await client.get(
            f"{config.api_url}/api/v1/items",
            params={"limit": 1, "artifact_source": "upload"},
        )
    resp.raise_for_status()
    data = resp.json().get("data", [])
    return data[0]["slug"] if data else None


async def discover_first_scan(config: Config) -> dict[str, Any] | None:
    """First scan summary (`id` + `aggregate_score` + …), or None when no scans."""
    async with make_client(config) as client:
        resp = await client.get(f"{config.api_url}/api/v1/scans", params={"limit": 1})
    resp.raise_for_status()
    data = resp.json().get("data", [])
    return data[0] if data else None
