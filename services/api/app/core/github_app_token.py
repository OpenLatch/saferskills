"""Shared GitHub App installation-token provider.

One identity, one budget: both the ingestion adapters (`app/ingestion/framework/
http_client.py`) and the scan-fetch path (`app/scan/fetch.py`) mint their
`Authorization` from here, so every outbound GitHub call shares the App's
5,000 req/h installation-token budget (vs the 60 req/h anonymous limit).

The token is minted by signing a short-lived RS256 JWT with the App private key,
exchanging it for a ~1h installation token, and caching that in-process for
50 minutes. Returns None when the App creds are absent (dev/test) — callers then
fall back to a PAT or anonymous.
"""

from __future__ import annotations

import time
from typing import Any

import httpx

from app.core.config import Settings

# In-process installation-token cache: {"token": (token, monotonic-expiry)}.
_GITHUB_APP_TOKEN: dict[str, tuple[str, float]] = {}


async def get_github_app_installation_token(settings: Settings) -> str | None:
    """Mint (and cache 50 min) a GitHub App installation token. None if creds absent."""
    app_id: str | None = getattr(settings, "github_app_id", None)
    private_key: str | None = getattr(settings, "github_app_private_key", None)
    installation_id: str | None = getattr(settings, "github_app_installation_id", None)
    if not (app_id and private_key and installation_id):
        return None
    cached = _GITHUB_APP_TOKEN.get("token")
    if cached is not None and cached[1] > time.monotonic() + 60.0:
        return cached[0]

    import jwt

    now = int(time.time())
    payload: dict[str, int | str] = {"iat": now - 30, "exp": now + 60 * 9, "iss": app_id}
    jwt_token: str = jwt.encode(payload, private_key, algorithm="RS256")
    async with httpx.AsyncClient(timeout=20.0) as raw:
        r = await raw.post(
            f"https://api.github.com/app/installations/{installation_id}/access_tokens",
            headers={
                "Authorization": f"Bearer {jwt_token}",
                "Accept": "application/vnd.github+json",
            },
        )
        r.raise_for_status()
        data: dict[str, Any] = r.json()
        token: str = data["token"]
    _GITHUB_APP_TOKEN["token"] = (token, time.monotonic() + 60 * 50)
    return token
