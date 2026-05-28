import { describe, expect, it } from 'vitest'
import type { CatalogHit } from '../../src/lib/catalog-search'
import { groupByKind, searchCatalog } from '../../src/lib/catalog-search'

describe('searchCatalog', () => {
  it('returns empty for empty / whitespace query', async () => {
    expect(await searchCatalog('')).toHaveLength(0)
    expect(await searchCatalog('   ')).toHaveLength(0)
  })

  it('matches case-insensitively on display_name', async () => {
    const hits = await searchCatalog('CLAUDE')
    expect(hits.length).toBeGreaterThan(0)
    for (const h of hits) {
      expect(h.display_name.toLowerCase()).toContain('claude')
    }
  })

  it('returns zero hits for nonsense queries', async () => {
    const hits = await searchCatalog('zzzzzzzz')
    expect(hits).toHaveLength(0)
  })

  it('matches substrings across kinds', async () => {
    const hits = await searchCatalog('mcp')
    const kinds = new Set(hits.map((h) => h.kind))
    expect(kinds.has('mcp_server')).toBe(true)
  })

  it('honours an aborted signal', async () => {
    const ctrl = new AbortController()
    ctrl.abort()
    await expect(searchCatalog('claude', ctrl.signal)).rejects.toMatchObject({
      name: 'AbortError',
    })
  })
})

describe('groupByKind', () => {
  const sample: CatalogHit[] = [
    {
      kind: 'mcp_server',
      slug: 'a',
      display_name: 'a',
      editor: 'cursor',
      scan_score: 80,
      severity: 'low',
    },
    {
      kind: 'skill',
      slug: 'b',
      display_name: 'b',
      editor: 'cursor',
      scan_score: 80,
      severity: 'low',
    },
    {
      kind: 'mcp_server',
      slug: 'c',
      display_name: 'c',
      editor: 'cursor',
      scan_score: 80,
      severity: 'low',
    },
  ]

  it('groups hits by kind and follows the canonical group order', () => {
    const groups = groupByKind(sample)
    expect(groups.map((g) => g.kind)).toEqual(['skill', 'mcp_server'])
    expect(groups[1].hits).toHaveLength(2)
  })

  it('drops empty groups', () => {
    const groups = groupByKind([sample[1]])
    expect(groups).toHaveLength(1)
    expect(groups[0].kind).toBe('skill')
  })

  it('caps each group at 8 rows', () => {
    const many: CatalogHit[] = Array.from({ length: 12 }, (_, i) => ({
      kind: 'skill',
      slug: `s-${i}`,
      display_name: `s-${i}`,
      editor: 'cursor',
      scan_score: 80,
      severity: 'low',
    }))
    const groups = groupByKind(many)
    expect(groups).toHaveLength(1)
    expect(groups[0].hits).toHaveLength(8)
  })
})
