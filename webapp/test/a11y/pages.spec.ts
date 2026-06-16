import AxeBuilder from '@axe-core/playwright'
import { expect, test } from '@playwright/test'

/**
 * WCAG 2 A/AA axe smoke over every public page that renders without seeded
 * data (D-FE-18). Item-detail + scan-report a11y run against the seeded
 * staging e2e since they require catalog data. Fails on any violation.
 */
// `/docs/*` is the Starlight SSG docs site (I-06), built separately and served
// by the Node server as a static fall-through. Its a11y + Lighthouse gate lives
// in the docs build (I-06 Plan 3), not in this main-site SSR smoke.
const PAGES = ['/', '/catalog', '/scan', '/about', '/methodology', '/404']

for (const path of PAGES) {
  test(`a11y: ${path}`, async ({ page }) => {
    await page.goto(path, { waitUntil: 'load' })
    // The homepage runs live-polling islands (HomepageLive / NavStars refresh on
    // an interval), so its network never goes idle and `networkidle` flakes out
    // at the 30s test timeout. Give islands a bounded moment to settle, then run
    // axe against the rendered DOM regardless of ongoing background fetches.
    await page.waitForLoadState('networkidle', { timeout: 4000 }).catch(() => {})
    const results = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa']).analyze()
    expect(results.violations).toEqual([])
  })
}
