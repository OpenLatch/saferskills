import { describe, expect, it } from 'vitest'

import { isIndexableScan } from '@/lib/tier'

// SEO-T9: the item page sets `noindex={!isIndexableScan(latest_scan)}`. This is
// the SAME predicate as the backend sitemap `_items` filter (`tier != 'unscoped'`),
// so the indexed set and the sitemap set can never drift. These cases pin the
// predicate that drives the `<meta name="robots" content="noindex">` on the page.
describe('item page indexability (noindex predicate)', () => {
  it('a never-scanned item (no latest_scan) is NOT indexable', () => {
    expect(isIndexableScan(null)).toBe(false)
    expect(isIndexableScan(undefined)).toBe(false)
  })

  it("a placeholder/pending scan (tier 'unscoped') is NOT indexable", () => {
    expect(isIndexableScan({ tier: 'unscoped' })).toBe(false)
  })

  it("a completed scan (tier != 'unscoped') IS indexable", () => {
    for (const tier of ['green', 'yellow', 'orange', 'red']) {
      expect(isIndexableScan({ tier })).toBe(true)
    }
  })
})
