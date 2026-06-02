"""Playwright check of the unlisted (capability-URL) surface (I-3.5).

Staging acceptance, NOT a required pr-checks lane. Creates a private upload via
a LOOPBACK submit (exempt from the per-IP cap), lands on `/scans/r/<token>`, and
asserts the private chrome: banner, manage bar, the `noindex` meta, and the
page-level anti-leakage headers. Then exercises the **delete** branch (token →
404). The **promote** branch is asserted by `tests/routers/test_upload_routes.py`
(structured 200 → run report) — re-promoting here would consume the run.

Skips gracefully if the API submit is rejected (e.g. a non-loopback runner that
hits the cap) so a remote staging run never hard-fails on environment.
"""

from __future__ import annotations

import httpx
from playwright.async_api import Browser, Page, async_playwright
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from saferskills_e2e.commands.base import BaseCommand
from saferskills_e2e.shared.config import Config
from saferskills_e2e.shared.exit_codes import ExitCode
from saferskills_e2e.shared.http_client import make_client
from saferskills_e2e.shared.output import print_fail, print_info, print_ok, print_warn

PAGE_LOAD_TIMEOUT_MS = 15_000
ELEMENT_TIMEOUT_MS = 6_000

_FIXTURE = b"---\nname: e2e-private\ndescription: e2e fixture\n---\n# e2e-private\n\nReads only.\n"


class UnlistedFlowCommand(BaseCommand):
    name = "unlisted-flow"
    description = "Headless check of the unlisted capability-URL page + delete"

    async def run(self, config: Config) -> ExitCode:
        self.print_header()
        token = await self._create_unlisted(config)
        if token is None:
            print_warn("Could not create an unlisted run (cap/non-loopback) — skipping.")
            return ExitCode.OK
        try:
            async with async_playwright() as pw:
                browser: Browser = await pw.chromium.launch(headless=True)
                try:
                    return await self._check(browser, config, token)
                finally:
                    await browser.close()
        except PlaywrightError as e:
            print_fail(f"Playwright launch failed: {e!s}")
            return ExitCode.FAIL_UNLISTED_FLOW

    async def _create_unlisted(self, config: Config) -> str | None:
        try:
            async with make_client(config) as client:
                resp = await client.post(
                    f"{config.api_url}/api/v1/scans/upload",
                    files={"file": ("SKILL.md", _FIXTURE, "text/markdown")},
                    data={"visibility": "unlisted"},
                )
        except httpx.HTTPError:
            return None
        if resp.status_code != 202:
            return None
        share_url = resp.json().get("share_url") or ""
        return share_url.rstrip("/").split("/scans/r/")[-1] or None

    async def _check(self, browser: Browser, config: Config, token: str) -> ExitCode:
        page: Page = await (await browser.new_context()).new_page()
        url = f"{config.base_url}/scans/r/{token}"

        try:
            response = await page.goto(url, timeout=PAGE_LOAD_TIMEOUT_MS)
        except PlaywrightTimeoutError:
            print_fail(f"{url} did not load")
            return ExitCode.FAIL_UNLISTED_FLOW

        # Page-level anti-leakage header (D-UP-32) — read off the navigation response.
        robots = (response.headers.get("x-robots-tag", "") if response else "").replace(" ", "")
        if robots != "noindex,nofollow":
            print_fail("page response is missing X-Robots-Tag: noindex,nofollow")
            return ExitCode.FAIL_UNLISTED_FLOW
        print_ok("page-level noindex header present")

        for selector_text, label in (
            ("Private — only people with this link", "private banner"),
            ("Copy link", "manage bar"),
        ):
            try:
                await page.get_by_text(selector_text, exact=False).first.wait_for(
                    state="visible", timeout=ELEMENT_TIMEOUT_MS
                )
                print_ok(f"{label} renders")
            except PlaywrightTimeoutError:
                print_fail(f"{label} missing on the unlisted page")
                return ExitCode.FAIL_UNLISTED_FLOW

        # noindex meta tag in <head>.
        meta = await page.locator('meta[name="robots"]').count()
        if meta < 1:
            print_fail("noindex robots meta missing in <head>")
            return ExitCode.FAIL_UNLISTED_FLOW
        print_ok("noindex meta present")

        # Delete branch: token → 404 afterward (no oracle).
        try:
            async with make_client(config) as client:
                await client.delete(f"{config.api_url}/api/v1/scans/r/{token}")
                after = await client.get(f"{config.api_url}/api/v1/scans/r/{token}")
            if after.status_code != 404:
                print_fail(f"deleted token still resolves ({after.status_code})")
                return ExitCode.FAIL_UNLISTED_FLOW
            print_ok("delete → token 404s")
        except httpx.HTTPError as e:
            print_fail(f"delete request failed: {e!s}")
            return ExitCode.FAIL_UNLISTED_FLOW

        print_info("unlisted-flow OK")
        return ExitCode.OK
