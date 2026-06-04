"""Robust HTTP client for the dashboard TUI.

Unlike `shared/http_client.call` (which `typer.Exit`s on error — fine for a
one-shot CLI command, fatal for a long-running TUI), this surfaces failures as a
plain `HealthClientError` the screens render as a red bar while keeping the last
good snapshot. Reuses `shared.http_client.create_client` for the X-Admin-Key gate.
"""

from __future__ import annotations

from typing import Any

import httpx

from ....shared.context import AdminContext
from ....shared.http_client import create_client


class HealthClientError(Exception):
    """A dashboard API call failed (transport or HTTP >=400)."""


class SourcesHealthClient:
    """Thin sync client over the eagle-eye admin endpoints."""

    def __init__(self, actx: AdminContext) -> None:
        self._actx = actx

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        try:
            with create_client(self._actx.api_url, self._actx.admin_key) as client:
                resp = client.request(method, path, **kwargs)
        except httpx.HTTPError as exc:
            raise HealthClientError(str(exc)) from exc
        if resp.status_code >= 400:
            detail = ""
            try:
                detail = resp.json().get("detail", "")
            except ValueError:
                detail = resp.text[:200]
            raise HealthClientError(f"HTTP {resp.status_code} {detail}".strip())
        if resp.status_code == 204 or not resp.content:
            return {}
        return resp.json()

    def snapshot(self) -> dict[str, Any]:
        """The full eagle-eye `GET /admin/sources` snapshot."""
        return self._request("GET", "/api/v1/admin/sources")

    def runs(self, source: str, *, before: str | None = None, limit: int = 50) -> dict[str, Any]:
        params: dict[str, Any] = {"limit": limit}
        if before:
            params["before"] = before
        return self._request("GET", f"/api/v1/admin/sources/{source}/runs", params=params)

    def force_cycle(self, source: str) -> dict[str, Any]:
        return self._request("POST", f"/api/v1/admin/sources/{source}/force-cycle")

    def pause(self, source: str) -> dict[str, Any]:
        return self._request("POST", f"/api/v1/admin/sources/{source}/pause", json={})

    def unpause(self, source: str) -> dict[str, Any]:
        return self._request("POST", f"/api/v1/admin/sources/{source}/unpause")
