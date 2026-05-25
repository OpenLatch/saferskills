"""Playwright homepage smoke.

Loads `<base_url>` in headless Chromium and asserts the public landing
page's contract:

  (a) The "SaferSkills" wordmark is visible.
  (b) An `<input type="email">` is present AND an enabled submit button
      labelled "Notify me" sits next to it.

A timestamped screenshot is written under `<repo_root>/.local/screenshots/`
on every run (pass or fail) so failed CI runs leave an artifact and
local runs accumulate a visual diary.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from playwright.async_api import (
    Browser,
    Locator,
    Page,
    async_playwright,
)
from playwright.async_api import (
    Error as PlaywrightError,
)
from playwright.async_api import (
    TimeoutError as PlaywrightTimeoutError,
)

from saferskills_e2e.commands.base import BaseCommand
from saferskills_e2e.shared.config import Config
from saferskills_e2e.shared.exit_codes import ExitCode
from saferskills_e2e.shared.output import print_fail, print_info, print_ok

WORDMARK = "SaferSkills"
SUBMIT_LABEL = "Notify me"
PAGE_LOAD_TIMEOUT_MS = 15_000
ELEMENT_TIMEOUT_MS = 5_000


class HomepageCommand(BaseCommand):
    name = "homepage"
    description = "Headless Chromium check of the public landing page"

    async def run(self, config: Config) -> ExitCode:
        self.print_header()

        screenshot_dir = config.ensure_screenshot_dir()

        try:
            async with async_playwright() as pw:
                browser: Browser = await pw.chromium.launch(headless=True)
                try:
                    return await self._run_in_browser(
                        browser, config, screenshot_dir
                    )
                finally:
                    await browser.close()
        except PlaywrightError as e:
            # Most commonly: "Executable doesn't exist" when the user
            # forgot `playwright install chromium`. Surface the error
            # verbatim so the install hint reaches the operator.
            print_fail(f"Playwright launch failed: {e!s}")
            return ExitCode.FAIL_HOMEPAGE

    async def _run_in_browser(
        self,
        browser: Browser,
        config: Config,
        screenshot_dir: Path,
    ) -> ExitCode:
        context = await browser.new_context()
        page: Page = await context.new_page()

        try:
            await page.goto(config.base_url, timeout=PAGE_LOAD_TIMEOUT_MS)
        except PlaywrightTimeoutError:
            print_fail(f"Homepage at {config.base_url} did not load within "
                       f"{PAGE_LOAD_TIMEOUT_MS} ms")
            await self._screenshot(page, screenshot_dir, suffix="load-timeout")
            return ExitCode.FAIL_HOMEPAGE

        # 1. Wordmark.
        try:
            await page.get_by_text(WORDMARK, exact=False).first.wait_for(
                state="visible", timeout=ELEMENT_TIMEOUT_MS
            )
            print_ok(f"Wordmark {WORDMARK!r} is visible")
        except PlaywrightTimeoutError:
            print_fail(f"Wordmark {WORDMARK!r} not visible on {config.base_url}")
            await self._screenshot(page, screenshot_dir, suffix="missing-wordmark")
            return ExitCode.FAIL_HOMEPAGE

        # 2a. Email input.
        email_input: Locator = page.locator('input[type="email"]').first
        try:
            await email_input.wait_for(state="visible", timeout=ELEMENT_TIMEOUT_MS)
            print_ok("Email input (<input type=\"email\">) is present")
        except PlaywrightTimeoutError:
            print_fail("No <input type=\"email\"> on the homepage")
            await self._screenshot(page, screenshot_dir, suffix="missing-email")
            return ExitCode.FAIL_HOMEPAGE

        # 2b. Submit button — match by accessible name so we tolerate
        # `<button>Notify me</button>`, `<input type="submit" value="Notify me">`,
        # and `aria-label="Notify me"` variants without coupling to the
        # exact markup choice.
        submit: Locator = page.get_by_role("button", name=SUBMIT_LABEL).first
        try:
            await submit.wait_for(state="visible", timeout=ELEMENT_TIMEOUT_MS)
        except PlaywrightTimeoutError:
            print_fail(f"No enabled submit button labelled {SUBMIT_LABEL!r}")
            await self._screenshot(page, screenshot_dir, suffix="missing-submit")
            return ExitCode.FAIL_HOMEPAGE

        if not await submit.is_enabled():
            print_fail(f"Submit button {SUBMIT_LABEL!r} is present but disabled")
            await self._screenshot(page, screenshot_dir, suffix="disabled-submit")
            return ExitCode.FAIL_HOMEPAGE
        print_ok(f"Submit button labelled {SUBMIT_LABEL!r} is enabled")

        screenshot_path = await self._screenshot(page, screenshot_dir, suffix="ok")
        print_info(f"Screenshot saved -> {screenshot_path}")

        return ExitCode.OK

    async def _screenshot(
        self, page: Page, screenshot_dir: Path, *, suffix: str
    ) -> Path:
        """Write a timestamped screenshot. Always called — success or
        failure — so artefacts accumulate predictably."""
        ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        path = screenshot_dir / f"homepage-{ts}-{suffix}.png"
        await page.screenshot(path=str(path), full_page=True)
        return path
