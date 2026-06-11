"""Playwright check of the dual-mode /scan upload affordance + the public
upload report (I-3.5).

Staging acceptance, NOT a required pr-checks lane. Two parts, both skip-friendly:

1. `/scan` renders with the **Capability** mode tab selected by default (the
   I-5.7 v3 umbrella page — the old Upload/Scan-repo inner tabs became the
   single pane with an "or paste a URL" divider), a DropZone, the
   public-default toggle, and the passive consent line. (UI presence — a live
   upload+scan is async + rate-limited, so it is asserted via the API contract
   in `tests/routers/test_upload_routes.py`, not here.)
2. If a public upload item exists in the catalog, its `/items/<slug>` page
   shows the upload provenance via the SaferSkills-built `.zip` download card
   (the stable SSR marker). Empty catalog → skip (fresh staging).
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
from saferskills_e2e.shared.output import print_fail, print_info, print_ok, print_warn

PAGE_LOAD_TIMEOUT_MS = 15_000
ELEMENT_TIMEOUT_MS = 5_000


class UploadFlowCommand(BaseCommand):
    name = "upload-flow"
    description = "Headless check of the /scan upload affordance + public upload report"

    async def run(self, config: Config) -> ExitCode:
        self.print_header()
        try:
            async with async_playwright() as pw:
                browser: Browser = await pw.chromium.launch(headless=True)
                try:
                    code = await self._check_scan_page(browser, config)
                    if code is not ExitCode.OK:
                        return code
                    return await self._check_upload_report(browser, config)
                finally:
                    await browser.close()
        except PlaywrightError as e:
            print_fail(f"Playwright launch failed: {e!s}")
            return ExitCode.FAIL_UPLOAD_FLOW

    async def _check_scan_page(self, browser: Browser, config: Config) -> ExitCode:
        page: Page = await (await browser.new_context()).new_page()
        url = f"{config.base_url}/scan"
        try:
            await page.goto(url, timeout=PAGE_LOAD_TIMEOUT_MS)
        except PlaywrightTimeoutError:
            print_fail(f"{url} did not load")
            return ExitCode.FAIL_UPLOAD_FLOW

        try:
            cap_tab = page.get_by_role("tab", name="Capability")
            await cap_tab.wait_for(state="visible", timeout=ELEMENT_TIMEOUT_MS)
            if await cap_tab.get_attribute("aria-selected") != "true":
                print_fail("Capability mode is not the default-selected tab")
                return ExitCode.FAIL_UPLOAD_FLOW
            print_ok("/scan defaults to the Capability mode")

            dropzone = page.locator("input[type='file']")
            await dropzone.first.wait_for(state="attached", timeout=ELEMENT_TIMEOUT_MS)
            print_ok("DropZone file input present")

            # The hidden Agent pane carries its own switch — assert the visible one.
            toggle = page.get_by_role("switch").locator("visible=true")
            await toggle.first.wait_for(state="visible", timeout=ELEMENT_TIMEOUT_MS)
            if await toggle.first.get_attribute("aria-checked") != "true":
                print_fail("Make-public toggle is not ON by default")
                return ExitCode.FAIL_UPLOAD_FLOW
            print_ok("public-by-default toggle present + ON")

            await page.get_by_text("published permanently", exact=False).first.wait_for(
                state="visible", timeout=ELEMENT_TIMEOUT_MS
            )
            print_ok("passive consent line present")
        except PlaywrightTimeoutError as e:
            print_fail(f"/scan upload affordance incomplete: {e!s}")
            return ExitCode.FAIL_UPLOAD_FLOW
        return ExitCode.OK

    async def _check_upload_report(self, browser: Browser, config: Config) -> ExitCode:
        try:
            slug = await discover_first_upload_item(config)
        except httpx.HTTPError as e:
            print_fail(f"Could not list upload items: {e!s}")
            return ExitCode.FAIL_UPLOAD_FLOW
        if slug is None:
            print_warn("No public upload items yet — skipping the upload-report assertions.")
            return ExitCode.OK

        page: Page = await (await browser.new_context()).new_page()
        url = f"{config.base_url}/items/{slug}"
        try:
            await page.goto(url, timeout=PAGE_LOAD_TIMEOUT_MS)
            await page.get_by_text("Download .zip", exact=False).first.wait_for(
                state="visible", timeout=ELEMENT_TIMEOUT_MS
            )
            print_ok(f"upload provenance (.zip download card) renders for {slug}")
        except PlaywrightTimeoutError:
            print_fail(f"upload provenance missing on {url}")
            return ExitCode.FAIL_UPLOAD_FLOW

        print_info("upload-flow OK")
        return ExitCode.OK
