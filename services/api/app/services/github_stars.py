"""Cached GitHub-stars proxy for the homepage `github_stars` metric.

One hourly, anonymous (or `GITHUB_TOKEN`-authenticated) call to
`api.github.com/repos/<repo>` reads `stargazers_count`. The value is memoized
in-process for ~1h (no Redis per `.claude/rules/tech-stack.md`). Any failure or
timeout returns ``None`` — the frontend then falls back to the launch
placeholder.

`api.github.com` is already on the outbound allowlist
(`.claude/rules/security.md` § Public-input handling) — no new host. The proxy
emits no PII: it caches a single integer count, never request metadata
(`.claude/rules/telemetry.md`).
"""

from __future__ import annotations

import logging
import time

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)

# The canonical SaferSkills repository whose stars back the NavBar GhStar count.
_REPO = "OpenLatch/saferskills"
_TTL_SECONDS = 3600.0
_TIMEOUT_SECONDS = 2.0

# Module-level timestamped cache: (fetched_at_monotonic, stars_or_none).
_cache: tuple[float, int | None] | None = None


def _auth_headers() -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "SaferSkills-Stats/0.1",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = get_settings().github_token
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


async def get_github_stars() -> int | None:
    """Return the repo's star count, cached ~1h. ``None`` on any failure."""
    global _cache
    now = time.monotonic()
    if _cache is not None and (now - _cache[0]) < _TTL_SECONDS:
        return _cache[1]

    stars: int | None = None
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
            resp = await client.get(
                f"https://api.github.com/repos/{_REPO}",
                headers=_auth_headers(),
            )
        if resp.status_code == 200:
            value = resp.json().get("stargazers_count")
            if isinstance(value, int):
                stars = value
        else:
            logger.warning("github stars proxy: HTTP %s", resp.status_code)
    except (httpx.HTTPError, ValueError) as exc:
        # Timeout, connection error, or malformed JSON — degrade to None.
        logger.warning("github stars proxy failed: %s", exc)

    _cache = (now, stars)
    return stars


def reset_cache() -> None:
    """Clear the memoized star count. Used by tests; harmless in production."""
    global _cache
    _cache = None
