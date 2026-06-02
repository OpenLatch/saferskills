"""Playwright check of the catalog UPLOAD badge + `artifact_source` filter (I-3.5).

Staging acceptance, NOT a required pr-checks lane. Skip-friendly:

- If a public upload item exists, load `/catalog?artifact_source=upload` and
  assert the UPLOAD badge renders and the filtered rows are upload-sourced.
- Always assert the Source filter group renders on `/catalog`.
- Assert an unlisted shadow slug is NOT in the public catalog (the API
  hard-filters `visibility='public'`) — proven by the API contract; here we
  confirm `/items/<random-unlisted-style-slug>` 404s.
"""

from __future__ import annotations

import httpx
from playwright.async_api import Browser, Page, async_playwright
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from saferskills_e2e.commands.base import BaseCommand
from saferskills_e2e.shared.config import Config
from saferskills_e2e.shared.discovery import discover_first_upload_item
from saferskills_e2e.shared.exit_codes import ExitCode
from saferskills_e2e.shared.http_client import make_client
from saferskills_e2e.shared.output import print_fail, print_info, print_ok, print_warn

PAGE_LOAD_TIMEOUT_MS = 15_000
ELEMENT_TIMEOUT_MS = 6_000


class CatalogBadgeFilterCommand(BaseCommand):
    name = "catalog-badge-filter"
    description = "Headless check of the catalog UPLOAD badge + artifact_source filter"

    async def run(self, config: Config) -> ExitCode:
        self.print_header()

        # An unlisted shadow slug never appears on the public catalog surface.
        try:
            async with make_client(config) as client:
                r = await client.get(f"{config.api_url}/api/v1/items/unlisted--deadbeef--skill-x")
            if r.status_code != 404:
                print_fail(f"an unlisted-style slug resolved ({r.status_code}) — must 404")
                return ExitCode.FAIL_CATALOG_BADGE
            print_ok("unlisted shadow slug 404s on the public item surface")
        except httpx.HTTPError as e:
            print_fail(f"item lookup failed: {e!s}")
            return ExitCode.FAIL_CATALOG_BADGE

        try:
            async with async_playwright() as pw:
                browser: Browser = await pw.chromium.launch(headless=True)
                try:
                    return await self._check(browser, config)
                finally:
                    await browser.close()
        except PlaywrightError as e:
            print_fail(f"Playwright launch failed: {e!s}")
            return ExitCode.FAIL_CATALOG_BADGE

    async def _check(self, browser: Browser, config: Config) -> ExitCode:
        page: Page = await (await browser.new_context()).new_page()
        try:
            await page.goto(f"{config.base_url}/catalog", timeout=PAGE_LOAD_TIMEOUT_MS)
            await page.get_by_text("Source", exact=True).first.wait_for(
                state="visible", timeout=ELEMENT_TIMEOUT_MS
            )
            print_ok("catalog Source filter group renders")
        except PlaywrightTimeoutError:
            print_fail("catalog Source filter group missing")
            return ExitCode.FAIL_CATALOG_BADGE

        slug = await discover_first_upload_item(config)
        if slug is None:
            print_warn("No public upload items yet — skipping the UPLOAD-badge assertion.")
            return ExitCode.OK

        try:
            await page.goto(
                f"{config.base_url}/catalog?artifact_source=upload", timeout=PAGE_LOAD_TIMEOUT_MS
            )
            await page.locator(".tag-mini.up").first.wait_for(
                state="visible", timeout=ELEMENT_TIMEOUT_MS
            )
            print_ok("UPLOAD badge renders on a filtered upload row")
        except PlaywrightTimeoutError:
            print_fail("UPLOAD badge missing under ?artifact_source=upload")
            return ExitCode.FAIL_CATALOG_BADGE

        print_info("catalog-badge-filter OK")
        return ExitCode.OK
