"""Access-log writer middleware (write-only — the reader ships later).

Write-only B2B-funnel signal. For a small closed set of public catalog actions it
records one `access_log` row with a /24-(v4) or /48-(v6) **redacted** IP, the
user-agent, and the referer host — never a raw IP, slug, URL, or PII (see
.claude/rules/privacy.md + security.md § Vendor-data isolation). The insert is
fire-and-forget so it never adds latency to or breaks the response.

`item_content_hash` is left NULL for now — the content-hash spine enrichment
lands with the reader; the action + redacted-IP signal accrues from day one.
"""

from __future__ import annotations

import asyncio
import contextlib
import ipaddress
from collections.abc import Awaitable, Callable

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.db.session import AsyncSessionLocal
from app.models import AccessLog

logger = structlog.get_logger(__name__)

_ITEMS_PREFIX = "/api/v1/items"
_RESERVED = {"facets"}  # /items/facets is not an item_view


def redact_ip(raw: str | None) -> str | None:
    """Mask to /24 (v4) or /48 (v6). Returns the network address string, or None."""
    if not raw:
        return None
    try:
        ip = ipaddress.ip_address(raw)
    except ValueError:
        return None
    prefix = 24 if ip.version == 4 else 48
    net = ipaddress.ip_network(f"{raw}/{prefix}", strict=False)
    return str(net.network_address)


def classify_action(method: str, path: str, has_query: bool) -> str | None:
    """Map a request to a closed-enum access_log action, or None to skip logging."""
    if method != "GET":
        return None
    if path == _ITEMS_PREFIX or path == _ITEMS_PREFIX + "/":
        return "catalog_search" if has_query else "catalog_filter"
    if path.startswith(_ITEMS_PREFIX + "/"):
        tail = path[len(_ITEMS_PREFIX) + 1 :]
        if "/" in tail:  # e.g. {slug}/download — not a plain item view
            return None
        if tail in _RESERVED:
            return None
        return "item_view"
    return None


class AccessLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        with contextlib.suppress(Exception):
            action = classify_action(request.method, request.url.path, bool(request.url.query))
            if action is not None and 200 <= response.status_code < 400:
                client_host = request.client.host if request.client else None
                referer = request.headers.get("referer")
                referer_host = None
                if referer:
                    from urllib.parse import urlparse

                    with contextlib.suppress(Exception):
                        referer_host = urlparse(referer).hostname or None
                ua = request.headers.get("user-agent")
                asyncio.create_task(  # noqa: RUF006 — fire-and-forget, best-effort
                    _write_access_log(
                        action=action,
                        ip=redact_ip(client_host),
                        user_agent=ua[:500] if ua else None,
                        referer_host=referer_host[:200] if referer_host else None,
                    )
                )
        return response


async def _write_access_log(
    *, action: str, ip: str | None, user_agent: str | None, referer_host: str | None
) -> None:
    try:
        async with AsyncSessionLocal() as session:
            session.add(
                AccessLog(
                    action=action,
                    ip=ip,
                    user_agent=user_agent,
                    http_referer_host=referer_host,
                    item_content_hash=None,
                )
            )
            await session.commit()
    except Exception:
        logger.debug("access_log.write_failed", action=action)
