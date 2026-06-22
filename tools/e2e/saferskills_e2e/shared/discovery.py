"""Catalog/scan discovery helpers for the smoke commands.

The item-detail / vendor-respond / badge / og commands all need to find a real
slug or scan from the running API (the catalog can be empty until data-seed
runs, so callers skip gracefully on `None`). Centralised here so the four
commands share one `make_client`-based fetch instead of re-rolling httpx.
"""

from __future__ import annotations

from typing import Any

from saferskills_e2e.shared.config import Config
from saferskills_e2e.shared.http_client import make_client, request_with_retries


async def _get_json(config: Config, path: str, params: dict[str, Any]) -> dict[str, Any]:
    """GET `path` with transient-retry, raise_for_status, and return the JSON body.

    Centralises the retry wiring so every discovery helper absorbs a transient
    staging blip (502/503/504/timeout) the same way — a sustained failure still
    raises `httpx.HTTPStatusError` (via `raise_for_status`) so the caller's command
    fails honestly."""
    async with make_client(config) as client:
        resp = await request_with_retries(
            client,
            "GET",
            f"{config.api_url}{path}",
            params=params,
            retries=config.retries,
            backoff=config.retry_backoff_seconds,
        )
    resp.raise_for_status()
    body: dict[str, Any] = resp.json()
    return body


async def discover_first_item_slug(config: Config) -> str | None:
    """Slug of the first catalog item, or None when the catalog is empty."""
    data = (await _get_json(config, "/api/v1/items", {"limit": 1})).get("data", [])
    return data[0]["slug"] if data else None


async def discover_first_upload_item(config: Config) -> str | None:
    """Slug of the first PUBLIC upload-sourced catalog item, or None.

    Uses the `artifact_source=upload` filter — empty on a fresh staging until an
    upload is published, so callers skip gracefully on `None`."""
    data = (
        await _get_json(config, "/api/v1/items", {"limit": 1, "artifact_source": "upload"})
    ).get("data", [])
    return data[0]["slug"] if data else None


async def discover_first_scan(config: Config) -> dict[str, Any] | None:
    """First scan summary (`id` + `aggregate_score` + …), or None when no scans."""
    data = (await _get_json(config, "/api/v1/scans", {"limit": 1})).get("data", [])
    return data[0] if data else None


async def discover_first_completed_scan(config: Config) -> dict[str, Any] | None:
    """First scan summary whose OG card will render, or None when none exist yet.

    The public `/scans` feed is filtered to public + non-firehose but NOT by
    status, so the newest row can be a pending/running/failed run; and the slim
    feed DTO (`ScanReportSummary`) exposes no `status` field. The OG card
    endpoint only serves a `completed` run (else 404), so the og-endpoint smoke
    must pick a row that is provably completed-and-scored. The reliable signal
    the DTO *does* carry is `tier` (= `repo_tier`): a non-completed run is
    `tier='unscoped'` with no `aggregate_score` (the same predicate the sitemap
    and the item `noindex` use). So select the first row with a real tier — that
    run's OG card 200s; otherwise the smoke would (correctly) get a 404 and
    false-fail."""
    for row in (await _get_json(config, "/api/v1/scans", {"limit": 20})).get("data", []):
        if row.get("tier") and row["tier"] != "unscoped" and row.get("aggregate_score") is not None:
            return row
    return None
