"""HTTP middleware for the SaferSkills API.

`StartupGuardMiddleware` rejects requests with 503 while the API is in degraded
mode (migrations failed at startup). The liveness path is bypassed so ops can
still observe *why* the service is degraded via `/api/v1/health`.

Implemented as **pure ASGI middleware** (`__init__(app)` / `__call__(scope,
receive, send)`), not a `BaseHTTPMiddleware` subclass. Starlette's docs warn
that `BaseHTTPMiddleware` spawns an extra anyio task per request bound to the
event loop that ran `__call__`; under pytest-asyncio's function-scoped loops,
re-running `ASGITransport(app=app)` against the same app instance leaks task
references across loops (the classic `attached to a different loop` flake).
Pure ASGI middleware spawns no background task, so no loop binding escapes the
request boundary. Keep this in pure-ASGI form.
"""

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from app.core.startup_state import startup_state


def service_unavailable_response(message: str) -> JSONResponse:
    """The canonical 503 body, shared so its shape never drifts across callers.

    Used by both the degraded-mode guard below (migrations failed at startup)
    and the pool-timeout back-pressure handler in `app/main.py` (crash-resilience
    §1.3). Same `code`, caller-specific `message`.
    """
    return JSONResponse(
        status_code=503,
        content={"detail": {"code": "SERVICE_UNAVAILABLE", "message": message}},
    )


class StartupGuardMiddleware:
    """Reject all API requests with 503 when migrations have failed.

    The liveness endpoint is allowed through so monitoring systems can observe
    the degraded state. All other endpoints get a clear 503.
    """

    # Paths that bypass the guard (liveness probe must always respond).
    _BYPASS_PATHS = frozenset({"/api/v1/health"})

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        if not startup_state.is_healthy and scope["path"] not in self._BYPASS_PATHS:
            response = service_unavailable_response(
                "API is in degraded mode — migrations failed at "
                "startup; see /api/v1/health for details."
            )
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)
