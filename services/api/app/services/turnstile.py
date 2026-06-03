"""Cloudflare Turnstile human-verification gate for the scan-submit endpoints.

A Turnstile token (minted client-side by the widget) is verified server-side
against Cloudflare's `siteverify` before any scan work begins. This complements
— never replaces — the per-IP rate limit (`scans.py`): the rate limit caps one
IP, the CAPTCHA raises the cost of distributed/bot abuse where every accepted
submission costs us a full scan.

Mirrors the httpx outbound pattern in `app/services/github_stars.py`.
`challenges.cloudflare.com` is a fixed, non-user-controlled host (outside the
github-only SSRF concern in `.claude/rules/security.md` § Public-input handling).

Degradation contract (two independent axes):

- **Unconfigured (no secret key)** → `verify_turnstile` returns ``True`` (bypass).
  This keeps dev/test/CI/loopback-seed flows working with no Cloudflare account.
  The config-layer startup guard (`config.py`) makes this safe by forbidding a
  missing secret in `staging`/`production`, so a real deploy can never silently
  run with the gate open.
- **Configured but Cloudflare unreachable** (timeout / HTTP error) → returns
  ``False`` (**fail-closed**). A Cloudflare blip must not open the gate to bots.
  This is a deliberate availability-vs-abuse tradeoff: a brief siteverify outage
  briefly rejects legitimate submitters rather than admitting unverified ones.
"""

from __future__ import annotations

import logging

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_SITEVERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
_TIMEOUT_SECONDS = 3.0


async def verify_turnstile(token: str | None, remoteip: str | None = None) -> bool:
    """Verify a Turnstile token via Cloudflare's `siteverify`.

    Returns ``True`` if the human-verification passes (or if no secret key is
    configured — the dev/test bypass guaranteed safe by the startup guard).
    Returns ``False`` if the token is missing/invalid, or if `siteverify` is
    unreachable while a secret IS set (fail-closed).

    `remoteip` is accepted but intentionally NOT sent on Fly: `request.client.host`
    is the 6PN proxy peer, not the end user (see `scans.py::_is_loopback`), so
    forwarding it would weaken — not strengthen — verification. The parameter is
    kept for a future `X-Forwarded-For`-based end-user IP resolution.
    """
    secret = get_settings().turnstile_secret_key
    if secret is None:
        # Unconfigured → bypass. Safe: the startup guard forbids this in prod/staging.
        return True
    if not token:
        return False

    payload = {"secret": secret, "response": token}
    if remoteip is not None:
        payload["remoteip"] = remoteip

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
            resp = await client.post(_SITEVERIFY_URL, data=payload)
        if resp.status_code != 200:
            logger.warning("turnstile siteverify: HTTP %s", resp.status_code)
            return False
        return bool(resp.json().get("success") is True)
    except (httpx.HTTPError, ValueError) as exc:
        # Timeout, connection error, or malformed JSON — fail closed (a blip
        # must never silently open the gate to bots).
        logger.warning("turnstile siteverify failed: %s", exc)
        return False
