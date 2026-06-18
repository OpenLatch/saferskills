"""robots.txt fetch + cache (Protego). Framework hook now; enforced by the
ScrapingAdapter (ToS-respect). Cached 24h per host.
"""

from __future__ import annotations

import time

import httpx
from protego import Protego

_CACHE: dict[str, tuple[Protego | None, float]] = {}
_TTL_SECONDS = 86_400
_UA = "SaferSkillsBot/1.0 (+https://saferskills.ai/bot)"


async def is_allowed(url: str, *, user_agent: str = _UA) -> bool:
    """Return True if `user_agent` may fetch `url` per the host's robots.txt.

    Fail-open on a robots.txt fetch error (treated as 'no rules' — the same posture
    most well-behaved crawlers take), but a present Disallow is always honoured.
    """
    parsed = httpx.URL(url)
    host_key = f"{parsed.scheme}://{parsed.host}"
    rp = await _get_robots(host_key)
    if rp is None:
        return True
    return rp.can_fetch(url, user_agent)


async def _get_robots(host_key: str) -> Protego | None:
    cached = _CACHE.get(host_key)
    now = time.monotonic()
    if cached is not None and cached[1] > now:
        return cached[0]
    rp: Protego | None = None
    try:
        async with httpx.AsyncClient(timeout=15.0, headers={"User-Agent": _UA}) as client:
            r = await client.get(f"{host_key}/robots.txt")
            if r.status_code == 200:
                rp = Protego.parse(r.text)
    except httpx.HTTPError, ValueError:
        rp = None
    _CACHE[host_key] = (rp, now + _TTL_SECONDS)
    return rp
