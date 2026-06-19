"""HTTP check of the OG image endpoint (/og/scan/<scan_id>.png).

Discovers a scan, requests its OG card, and asserts 200 + `image/png` + the
PNG magic header. Empty scans list → skip (OK).
"""

from __future__ import annotations

import httpx

from saferskills_e2e.commands.base import BaseCommand
from saferskills_e2e.shared.config import Config
from saferskills_e2e.shared.discovery import discover_first_completed_scan
from saferskills_e2e.shared.exit_codes import ExitCode
from saferskills_e2e.shared.http_client import make_client
from saferskills_e2e.shared.output import print_fail, print_ok, print_warn

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


class OgEndpointCommand(BaseCommand):
    name = "og-endpoint"
    description = "HTTP check of the OG image endpoint"

    async def run(self, config: Config) -> ExitCode:
        self.print_header()
        try:
            scan = await discover_first_completed_scan(config)
        except httpx.HTTPError as e:
            print_fail(f"Could not list scans: {e!s}")
            return ExitCode.FAIL_OG

        if scan is None:
            print_warn("No completed scans yet — skipping og-endpoint.")
            return ExitCode.OK

        scan_id = scan["id"]
        url = f"{config.base_url}/og/scan/{scan_id}.png"
        async with make_client(config) as client:
            resp = await client.get(url)
        if resp.status_code != 200:
            print_fail(f"og endpoint returned {resp.status_code} for {url}")
            return ExitCode.FAIL_OG
        if "image/png" not in resp.headers.get("content-type", ""):
            print_fail(f"og content-type was {resp.headers.get('content-type')!r}")
            return ExitCode.FAIL_OG
        if not resp.content.startswith(PNG_MAGIC):
            print_fail("og body is not a valid PNG")
            return ExitCode.FAIL_OG
        print_ok(f"OG image renders for scan {scan_id} ({len(resp.content)} bytes)")

        return ExitCode.OK
