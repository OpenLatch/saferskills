import AxeBuilder from '@axe-core/playwright'
import { expect, test } from '@playwright/test'

/**
 * WCAG 2 A/AA axe smoke over every public page that renders without seeded
 * data (D-FE-18). Item-detail + scan-report a11y run against the seeded
 * staging e2e since they require catalog data. Fails on any violation.
 */
const PAGES = ['/', '/catalog', '/scan', '/about', '/docs', '/methodology', '/404']

for (const path of PAGES) {
  test(`a11y: ${path}`, async ({ page }) => {
    await page.goto(path, { waitUntil: 'networkidle' })
    const results = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa']).analyze()
    expect(results.violations).toEqual([])
  })
}
