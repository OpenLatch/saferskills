from __future__ import annotations

import httpx


def create_client(api_url: str, api_key: str | None = None) -> httpx.Client:
    """Build a sync httpx client pointed at the SaferSkills API."""
    headers: dict[str, str] = {
        "User-Agent": "saferskills-data-seed/0.1.0",
        "Accept": "application/json",
    }
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return httpx.Client(
        base_url=api_url.rstrip("/"),
        headers=headers,
        timeout=httpx.Timeout(connect=5.0, read=30.0, write=10.0, pool=5.0),
        follow_redirects=False,
    )


def create_scans_client(api_url: str, api_key: str | None = None) -> httpx.Client:
    """Alias for the catalog publisher; same configuration for now."""
    return create_client(api_url, api_key)
