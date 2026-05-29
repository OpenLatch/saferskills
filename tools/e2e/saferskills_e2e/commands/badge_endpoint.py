"""HTTP check of the badge SVG endpoint (/badge/<scan_id>/<score>.svg).

Discovers a scan from `GET /api/v1/scans?limit=1`, requests its badge, and
asserts a 200 + `image/svg+xml` + an `<svg` body. Also asserts a tampered
score returns 400. Empty scans list → skip (OK).
"""

from __future__ import annotations

import httpx

from saferskills_e2e.commands.base import BaseCommand
from saferskills_e2e.shared.config import Config
from saferskills_e2e.shared.discovery import discover_first_scan
from saferskills_e2e.shared.exit_codes import ExitCode
from saferskills_e2e.shared.http_client import make_client
from saferskills_e2e.shared.output import print_fail, print_ok, print_warn


class BadgeEndpointCommand(BaseCommand):
    name = "badge-endpoint"
    description = "HTTP check of the badge SVG endpoint"

    async def run(self, config: Config) -> ExitCode:
        self.print_header()
        try:
            scan = await discover_first_scan(config)
        except httpx.HTTPError as e:
            print_fail(f"Could not list scans: {e!s}")
            return ExitCode.FAIL_BADGE

        if scan is None:
            print_warn("No scans yet — skipping badge-endpoint.")
            return ExitCode.OK

        scan_id, score = scan["id"], scan["aggregate_score"]
        url = f"{config.base_url}/badge/{scan_id}/{score}.svg"

        async with make_client(config) as client:
            resp = await client.get(url)
            if resp.status_code != 200:
                print_fail(f"badge returned {resp.status_code} for {url}")
                return ExitCode.FAIL_BADGE
            if "image/svg+xml" not in resp.headers.get("content-type", ""):
                print_fail(f"badge content-type was {resp.headers.get('content-type')!r}")
                return ExitCode.FAIL_BADGE
            if "<svg" not in resp.text:
                print_fail("badge body is not an SVG")
                return ExitCode.FAIL_BADGE
            print_ok(f"badge renders for scan {scan_id} ({score}/100)")

            tampered = await client.get(f"{config.base_url}/badge/{scan_id}/999.svg")
            if tampered.status_code != 400:
                print_fail(f"tampered score should be 400, got {tampered.status_code}")
                return ExitCode.FAIL_BADGE
            print_ok("tampered score correctly rejected (400)")

        return ExitCode.OK
