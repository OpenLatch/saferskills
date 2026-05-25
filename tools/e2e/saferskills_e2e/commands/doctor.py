"""Reachability check — pings the API and the marketing site.

Surfaces per-target latency so an operator can tell at a glance which
side of the stack is slow / down. Returns `OK` only when both targets
respond with a non-5xx status.
"""

from __future__ import annotations

import httpx

from saferskills_e2e.commands.base import BaseCommand
from saferskills_e2e.shared.config import Config
from saferskills_e2e.shared.exit_codes import ExitCode
from saferskills_e2e.shared.http_client import make_client
from saferskills_e2e.shared.output import (
    print_fail,
    print_info,
    print_ok,
    print_table,
)
from saferskills_e2e.shared.timing import Stopwatch


class DoctorCommand(BaseCommand):
    name = "doctor"
    description = "Reachability + latency probe for the API and marketing site"

    async def run(self, config: Config) -> ExitCode:
        self.print_header()

        rows: list[tuple[str, str, str, str]] = []  # target, url, status, latency_ms
        all_ok = True

        async with make_client(config) as client:
            for target, url in (
                ("API", f"{config.api_url}/api/v1/health"),
                ("Site", f"{config.base_url}/"),
            ):
                ok, status, latency_ms = await self._probe(client, url)
                rows.append((target, url, status, f"{latency_ms:.1f}"))
                if ok:
                    print_ok(f"{target} reachable ({status}, {latency_ms:.1f} ms)")
                else:
                    print_fail(f"{target} unreachable: {status}")
                    all_ok = False

        print_info("")
        print_table(rows, headers=("Target", "URL", "Status", "Latency (ms)"))

        return ExitCode.OK if all_ok else ExitCode.FAIL_REACHABILITY

    async def _probe(
        self, client: httpx.AsyncClient, url: str
    ) -> tuple[bool, str, float]:
        """Issue a GET and return `(ok, status_string, elapsed_ms)`.

        `ok` is True when we got *any* HTTP response with a status
        below 500 — 4xx is "reachable but unhappy" which is fine for
        reachability. Transport errors (DNS, refused, timeout) are the
        actual reachability failures.
        """
        with Stopwatch() as sw:
            try:
                resp = await client.get(url)
            except httpx.HTTPError as e:
                return False, f"transport error: {e!s}", sw.elapsed_ms
        ok = resp.status_code < 500
        return ok, f"HTTP {resp.status_code}", sw.elapsed_ms
