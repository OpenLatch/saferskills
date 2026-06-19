import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { ItemDetailResponse } from '@/lib/api/items'

// Mock the data layer + the (heavy, font-loading) OG renderer so the endpoint's
// guard logic is the unit under test — never the satori/resvg pipeline.
vi.mock('@/lib/api/items', () => ({ fetchItemBySlug: vi.fn() }))
vi.mock('@/lib/og', () => ({
  OG_HEADERS: { 'Content-Type': 'image/png' },
  renderOgCard: vi.fn(async () => Buffer.from([0x89, 0x50, 0x4e, 0x47])),
}))

const { fetchItemBySlug } = await import('@/lib/api/items')
const { renderOgCard } = await import('@/lib/og')
const { GET } = await import('@/pages/og/item/[slug].png')

type Ctx = Parameters<typeof GET>[0]
const ctx = (slug: string): Ctx => ({ params: { slug } }) as unknown as Ctx

/** Minimal item detail — the endpoint reads only `item.display_name` +
 * `latest_scan` (via `isIndexableScan`, which inspects `.tier`). */
function detail(tier: string | null): ItemDetailResponse {
  return {
    item: { display_name: 'acme-skill' },
    latest_scan: tier == null ? null : { tier },
  } as unknown as ItemDetailResponse
}

const mockItem = vi.mocked(fetchItemBySlug)
const mockRender = vi.mocked(renderOgCard)

describe('GET /og/item/<slug>.png', () => {
  beforeEach(() => {
    mockItem.mockReset()
    mockRender.mockClear()
  })
  afterEach(() => vi.restoreAllMocks())

  it('renders a 200 PNG for an item with a completed (scored) scan', async () => {
    for (const tier of ['green', 'yellow', 'orange', 'red']) {
      mockItem.mockResolvedValue(detail(tier))
      const res = await GET(ctx('acme--kit--skill-x'))
      expect(res.status).toBe(200)
      expect(res.headers.get('content-type')).toBe('image/png')
    }
  })

  it('404s an unscanned item (no latest_scan) — falls back to the branded card', async () => {
    mockItem.mockResolvedValue(detail(null))
    const res = await GET(ctx('acme--kit--skill-x'))
    expect(res.status).toBe(404)
    expect(mockRender).not.toHaveBeenCalled()
  })

  it("404s a placeholder scan (tier 'unscoped', noindex)", async () => {
    mockItem.mockResolvedValue(detail('unscoped'))
    const res = await GET(ctx('acme--kit--skill-x'))
    expect(res.status).toBe(404)
    expect(mockRender).not.toHaveBeenCalled()
  })

  it('404s a missing item', async () => {
    mockItem.mockResolvedValue(null)
    const res = await GET(ctx('nope'))
    expect(res.status).toBe(404)
  })

  it('400s a request with no slug param', async () => {
    const res = await GET(ctx(''))
    expect(res.status).toBe(400)
    expect(mockItem).not.toHaveBeenCalled()
  })
})
