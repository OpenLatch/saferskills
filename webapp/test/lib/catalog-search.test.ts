import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { CatalogItemSummary, CatalogListResponse } from '../../src/lib/api/items'
import type { CatalogHit } from '../../src/lib/catalog-search'

// Mock at the HTTP-client boundary — unit tests never hit the network
// (`.claude/rules/testing.md` § Async / network discipline).
const { listCatalogItems } = vi.hoisted(() => ({ listCatalogItems: vi.fn() }))
vi.mock('../../src/lib/api/items', () => ({ listCatalogItems }))

const { groupByKind, searchCatalog } = await import('../../src/lib/catalog-search')

function summary(over: Partial<CatalogItemSummary>): CatalogItemSummary {
  return {
    id: 'id',
    slug: 'slug',
    kind: 'skill',
    display_name: 'name',
    github_org: 'org',
    github_repo: 'repo',
    source_kind: 'github',
    popularity_tier: 'indexed',
    popularity_score: 0,
    latest_scan_score: 80,
    latest_scan_tier: 'green',
    findings_count: 0,
    registries: [],
    agent_compatibility: ['claude-code'],
    updated_at: '2026-06-02T00:00:00Z',
    ...over,
  }
}

function listResponse(data: CatalogItemSummary[]): CatalogListResponse {
  return {
    data,
    next_cursor: null,
    total_count: data.length,
    page: 1,
    total_pages: 1,
    page_size: data.length,
  }
}

describe('searchCatalog', () => {
  beforeEach(() => {
    listCatalogItems.mockReset()
    listCatalogItems.mockResolvedValue(listResponse([]))
  })

  it('returns empty for empty / whitespace query without hitting the API', async () => {
    expect(await searchCatalog('')).toHaveLength(0)
    expect(await searchCatalog('   ')).toHaveLength(0)
    expect(listCatalogItems).not.toHaveBeenCalled()
  })

  it('passes the trimmed query to the live catalog API', async () => {
    await searchCatalog('  claude  ')
    expect(listCatalogItems).toHaveBeenCalledWith(expect.objectContaining({ q: 'claude' }))
  })

  it('maps API summaries to dropdown hits', async () => {
    listCatalogItems.mockResolvedValue(
      listResponse([
        summary({ slug: 'github-mcp', kind: 'mcp_server', latest_scan_tier: 'orange' }),
      ])
    )
    const [hit] = await searchCatalog('mcp')
    expect(hit).toMatchObject({
      slug: 'github-mcp',
      kind: 'mcp_server',
      editor: 'claude-code',
      scan_score: 80,
      severity: 'medium',
    })
  })

  // Regression: a public UPLOAD-sourced item must surface in the hero
  // typeahead. Before the fix this searched a static mock that excluded
  // every real/uploaded catalog row.
  it('surfaces a public upload-sourced item', async () => {
    listCatalogItems.mockResolvedValue(
      listResponse([
        summary({
          slug: 'upload--a121b2d8--skill-canvas-design',
          display_name: 'canvas-design',
          source_kind: 'upload',
          latest_scan_score: 100,
        }),
      ])
    )
    const hits = await searchCatalog('canvas')
    expect(hits).toHaveLength(1)
    expect(hits[0].display_name).toBe('canvas-design')
  })

  it('honours an aborted signal', async () => {
    const ctrl = new AbortController()
    ctrl.abort()
    await expect(searchCatalog('claude', ctrl.signal)).rejects.toMatchObject({
      name: 'AbortError',
    })
    expect(listCatalogItems).not.toHaveBeenCalled()
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
