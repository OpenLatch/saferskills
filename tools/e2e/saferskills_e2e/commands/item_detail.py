"""Playwright check of the item-detail page (/items/<slug>).

Discovers a slug from `GET /api/v1/items?limit=1`. The catalog is empty at
I-03 ship (data-seed populates on demand), so an empty catalog is NOT a
failure — the command prints a warning and returns OK. With a slug present it
asserts the page-head identity title renders.
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
from saferskills_e2e.shared.output import print_fail, print_info, print_ok, print_warn

PAGE_LOAD_TIMEOUT_MS = 15_000
ELEMENT_TIMEOUT_MS = 5_000


class ItemDetailCommand(BaseCommand):
    name = "item-detail"
    description = "Headless Chromium check of the item-detail page"

    async def run(self, config: Config) -> ExitCode:
        self.print_header()
        try:
            slug = await discover_first_item_slug(config)
        except httpx.HTTPError as e:
            print_fail(f"Could not list items: {e!s}")
            return ExitCode.FAIL_ITEM_DETAIL

        if slug is None:
            print_warn("Catalog is empty — skipping item-detail (run data-seed to populate).")
            return ExitCode.OK

        url = f"{config.base_url}/items/{slug}"
        try:
            async with async_playwright() as pw:
                browser: Browser = await pw.chromium.launch(headless=True)
                try:
                    return await self._check(browser, config, url, slug)
                finally:
                    await browser.close()
        except PlaywrightError as e:
            print_fail(f"Playwright launch failed: {e!s}")
            return ExitCode.FAIL_ITEM_DETAIL

    async def _check(self, browser: Browser, config: Config, url: str, slug: str) -> ExitCode:
        del config
        page: Page = await (await browser.new_context()).new_page()
        try:
            await page.goto(url, timeout=PAGE_LOAD_TIMEOUT_MS)
        except PlaywrightTimeoutError:
            print_fail(f"{url} did not load")
            return ExitCode.FAIL_ITEM_DETAIL

        for selector, label in (
            (".ph-title", "identity title"),
            (".page-head", "page head"),
        ):
            try:
                await page.locator(selector).first.wait_for(
                    state="visible", timeout=ELEMENT_TIMEOUT_MS
                )
                print_ok(f"{label} renders for {slug}")
            except PlaywrightTimeoutError:
                print_fail(f"{label} missing on {url}")
                return ExitCode.FAIL_ITEM_DETAIL

        print_info(f"item-detail OK for {slug}")
        return ExitCode.OK
