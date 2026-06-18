import AxeBuilder from '@axe-core/playwright'
import { expect, test } from '@playwright/test'

/**
 * WCAG 2 A/AA axe smoke over the docs P0 pages (I-06). The native docs (I-06
 * rebuild) prerender into dist/client/docs and are served by the main Node app
 * on :5173, so the `lighthouse-a11y` CI lane runs this spec alongside
 * `pages.spec.ts` against that same :5173 server (baseURL defaults to :5173).
 * Fails on any violation.
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
