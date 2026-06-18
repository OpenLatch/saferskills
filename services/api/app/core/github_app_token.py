"""Shared GitHub App installation-token provider.

One identity, one budget: both the ingestion adapters (`app/ingestion/framework/
http_client.py`) and the scan-fetch path (`app/scan/fetch.py`) mint their
`Authorization` from here, so every outbound GitHub call shares the App's
5,000 req/h installation-token budget (vs the 60 req/h anonymous limit).

The token is minted by signing a short-lived RS256 JWT with the App private key,
exchanging it for a ~1h installation token, and caching that in-process for
50 minutes. Returns None when the App creds are absent (dev/test) — callers then
fall back to a PAT or anonymous.

Robustness: the mint is the SINGLE
point through which a GitHub-App outage reaches every outbound GitHub call — via
the `http_client._github_app_token_hook` request hook AND via `fetch.resolve_ref`
on the scan path (where a raised `httpx.HTTPStatusError`/`KeyError` is NOT a
`FetchError` and would bubble out as an unhandled traceback). So a failed mint
(401/403/5xx, malformed JSON, missing `token` key, JWT-sign error) is caught
here → ONE clean WARN → `None` (callers already fall back to anonymous). A short
in-process negative cache stops a failing mint from being retried on every
request during an outage.
"""

from __future__ import annotations

import time
from typing import Any

import httpx
import structlog

from app.core.config import Settings

logger = structlog.get_logger(__name__)

# In-process installation-token cache: {"token": (token, monotonic-expiry)}.
_GITHUB_APP_TOKEN: dict[str, tuple[str, float]] = {}

# Negative cache: monotonic timestamp until which a failed mint is NOT retried
# (so a GitHub-App outage doesn't re-attempt + re-log on every outbound request).
# A mutable container avoids a module-level `global` reassignment.
_MINT_STATE: dict[str, float] = {"failed_until": 0.0}
_NEGATIVE_CACHE_SECONDS = 60.0


async def get_github_app_installation_token(settings: Settings) -> str | None:
    """Mint (and cache 50 min) a GitHub App installation token. None if creds absent
    OR the mint fails (callers fall back to anonymous). Never raises."""
    app_id: str | None = getattr(settings, "github_app_id", None)
    private_key: str | None = getattr(settings, "github_app_private_key", None)
    installation_id: str | None = getattr(settings, "github_app_installation_id", None)
    if not (app_id and private_key and installation_id):
        return None
    cached = _GITHUB_APP_TOKEN.get("token")
    if cached is not None and cached[1] > time.monotonic() + 60.0:
        return cached[0]

    # Negative cache — during an outage, don't re-attempt + re-log every request.
    if time.monotonic() < _MINT_STATE["failed_until"]:
        return None

    try:
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
    except Exception as exc:
        # 401/403/5xx mint, malformed JSON, missing `token` key, JWT-sign error —
        # all become ONE clean WARN + a graceful None (caller → anonymous). A
        # traceback here would surface through every GitHub fetch on both the
        # ingestion and scan paths. Set the negative cache so an outage is quiet.
        status = exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else None
        logger.warning(
            "github_app_token.mint_failed",
            status=status,
            error_class=type(exc).__name__,
            error=str(exc)[:200],
        )
        _MINT_STATE["failed_until"] = time.monotonic() + _NEGATIVE_CACHE_SECONDS
        return None

    _GITHUB_APP_TOKEN["token"] = (token, time.monotonic() + 60 * 50)
    _MINT_STATE["failed_until"] = 0.0  # success clears any prior negative-cache window
    return token
