import AxeBuilder from '@axe-core/playwright'
import { expect, test } from '@playwright/test'

/**
 * WCAG 2 A/AA axe smoke over the docs P0 pages (I-06 Plan 3). The Starlight SSG
 * docs site is built + served by `astro preview` on :5174 in the `docs-a11y` CI
 * lane (PUBLIC_SITE_URL points the shared playwright.config baseURL there). This
 * file is invoked ONLY by that lane (`playwright test test/a11y/docs.spec.ts`);
 * the main `lighthouse-a11y` lane runs `pages.spec.ts` against the SSR site on
 * :5173, where /docs is not folded in. Fails on any violation.
 */
const PAGES = [
  '/docs/',
  '/docs/getting-started/quickstart/',
  '/docs/security-and-methodology/how-scoring-works/',
]

for (const path of PAGES) {
  test(`a11y(docs): ${path}`, async ({ page }) => {
    await page.goto(path, { waitUntil: 'load' })
    await page.waitForLoadState('networkidle', { timeout: 4000 }).catch(() => {})
    const results = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa']).analyze()
    expect(results.violations).toEqual([])
  })
}
