"""Playwright check of the vendor right-of-reply page (/items/<slug>/respond).

Asserts the unverified "Verify yourself" challenge renders (the "Issue
verification token" button). The full redeem→submit loop requires committing
a token to a real repo, which can't run in CI — that path is covered by the
backend integration test `tests/routers/test_vendor.py`. Empty catalog → skip.
"""

from __future__ import annotations

import httpx
from playwright.async_api import Browser, Page, async_playwright
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from saferskills_e2e.commands.base import BaseCommand
from saferskills_e2e.shared.config import Config
from saferskills_e2e.shared.discovery import discover_first_item_slug
from saferskills_e2e.shared.exit_codes import ExitCode
from saferskills_e2e.shared.output import print_fail, print_ok, print_warn

PAGE_LOAD_TIMEOUT_MS = 15_000
ELEMENT_TIMEOUT_MS = 5_000
ISSUE_BUTTON = "Issue verification token"


class VendorRespondCommand(BaseCommand):
    name = "vendor-respond"
    description = "Headless Chromium check of the vendor right-of-reply page"

    async def run(self, config: Config) -> ExitCode:
        self.print_header()
        try:
            slug = await discover_first_item_slug(config)
        except httpx.HTTPError as e:
            print_fail(f"Could not list items: {e!s}")
            return ExitCode.FAIL_VENDOR_RESPOND

        if slug is None:
            print_warn("Catalog is empty — skipping vendor-respond (run data-seed to populate).")
            return ExitCode.OK

        url = f"{config.base_url}/items/{slug}/respond"
        try:
            async with async_playwright() as pw:
                browser: Browser = await pw.chromium.launch(headless=True)
                try:
                    return await self._check(browser, url, slug)
                finally:
                    await browser.close()
        except PlaywrightError as e:
            print_fail(f"Playwright launch failed: {e!s}")
            return ExitCode.FAIL_VENDOR_RESPOND

    async def _check(self, browser: Browser, url: str, slug: str) -> ExitCode:
        page: Page = await (await browser.new_context()).new_page()
        try:
            await page.goto(url, timeout=PAGE_LOAD_TIMEOUT_MS)
        except PlaywrightTimeoutError:
            print_fail(f"{url} did not load")
            return ExitCode.FAIL_VENDOR_RESPOND

        try:
            await page.get_by_role("button", name=ISSUE_BUTTON).first.wait_for(
                state="visible", timeout=ELEMENT_TIMEOUT_MS
            )
            print_ok(f"verify challenge renders for {slug}")
        except PlaywrightTimeoutError:
            print_fail(f"verify challenge button {ISSUE_BUTTON!r} missing on {url}")
            return ExitCode.FAIL_VENDOR_RESPOND

        return ExitCode.OK
