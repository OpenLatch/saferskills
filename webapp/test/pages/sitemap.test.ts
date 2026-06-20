import { describe, expect, it, vi } from 'vitest'

// The static shard enumerates the webapp's own prerendered routes + the docs
// collection. Mock `astro:content` so the builder is unit-testable without the
// Astro content pipeline. Two docs entries: a section index (`install/index`)
// and a leaf (`install/cli-reference`) — exercising `idToSlug`.
vi.mock('astro:content', () => ({
  getCollection: vi.fn(async () => [
    { id: 'install/index', data: {} },
    { id: 'install/cli-reference', data: {} },
    { id: 'index', data: {} },
  ]),
}))

const { renderStaticShard, STATIC_ROUTES } = await import('@/lib/seo/static-sitemap')

describe('static sitemap shard', () => {
  it('includes the canonical marketing routes', async () => {
    const xml = await renderStaticShard()
    expect(xml).toContain('<loc>https://saferskills.ai/</loc>')
    expect(xml).toContain('<loc>https://saferskills.ai/capabilities</loc>')
    expect(xml).toContain('<loc>https://saferskills.ai/agents</loc>')
    // `/research/...` is intentionally absent — that page ships in plan 03; a
    // sitemap loc to a 404 would be a crawl-quality regression.
    expect(xml).not.toContain('saferskills.ai/research')
  })

  it('includes every docs slug via idToSlug', async () => {
    const xml = await renderStaticShard()
    // `install/index` collapses to `/docs/install/`; the leaf stays full.
    expect(xml).toContain('<loc>https://saferskills.ai/docs/install/</loc>')
    expect(xml).toContain('<loc>https://saferskills.ai/docs/install/cli-reference/</loc>')
    // The root index collapses to `/docs/`.
    expect(xml).toContain('<loc>https://saferskills.ai/docs/</loc>')
  })

  it('excludes token / api / media / redirect surfaces', async () => {
    const xml = await renderStaticShard()
    for (const excluded of [
      '/scans/r/',
      '/agents/r/',
      '/api/',
      '/og/',
      '/badge/',
      '/catalog',
      '/404',
      '/500',
    ]) {
      expect(xml).not.toContain(`saferskills.ai${excluded}`)
    }
  })

  it('emits valid <urlset> XML with NO lastmod (build-time is not a real mtime)', async () => {
    const xml = await renderStaticShard()
    expect(xml.startsWith('<?xml version="1.0" encoding="UTF-8"?>')).toBe(true)
    expect(xml).toContain('xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"')
    const urlCount = (xml.match(/<url>/g) ?? []).length
    expect(urlCount).toBe(STATIC_ROUTES.length + 3) // marketing + 3 mocked docs
    // R6: no synthetic lastmod on the static URLs (the DB shards carry the real one).
    expect(xml).not.toContain('<lastmod>')
  })
})
