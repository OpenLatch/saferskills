import { describe, expect, it } from 'vitest'

import {
  breadcrumbJsonLd,
  capabilityAppJsonLd,
  datasetJsonLd,
  organizationJsonLd,
  scannerAppJsonLd,
  serializeJsonLd,
} from '@/lib/jsonld'

// SEO-T4 + D-07-05. The builders are pure; these pins guard the structured-data
// contract (valid @type, NO fabricated AggregateRating, 1-indexed breadcrumb).
describe('jsonld builders', () => {
  it('organizationJsonLd is an Organization with a name + url', () => {
    const o = organizationJsonLd()
    expect(o['@type']).toBe('Organization')
    expect(o.name).toBe('SaferSkills')
    expect(o.url).toBe('https://saferskills.ai')
  })

  it('scannerAppJsonLd is a free SoftwareApplication', () => {
    const a = scannerAppJsonLd()
    expect(a['@type']).toBe('SoftwareApplication')
    expect(a.applicationCategory).toBe('SecurityApplication')
    // Free + open source — a $0 Offer.
    expect(a.offers).toMatchObject({ '@type': 'Offer', price: '0', priceCurrency: 'USD' })
  })

  it('capabilityAppJsonLd maps mcp_server → SoftwareApplication, else → SoftwareSourceCode', () => {
    const mcp = capabilityAppJsonLd({ slug: 's', name: 'srv', kind: 'mcp_server' })
    expect(mcp['@type']).toBe('SoftwareApplication')
    for (const kind of ['skill', 'hook', 'plugin', 'rules']) {
      const code = capabilityAppJsonLd({ slug: 's', name: 'n', kind })
      expect(code['@type']).toBe('SoftwareSourceCode')
    }
  })

  it('capabilityAppJsonLd carries the canonical url + optional codeRepository', () => {
    const withRepo = capabilityAppJsonLd({
      slug: 'acme--kit--skill-x',
      name: 'x',
      kind: 'skill',
      repoUrl: 'https://github.com/acme/kit',
    })
    expect(withRepo.url).toBe('https://saferskills.ai/items/acme--kit--skill-x')
    expect((withRepo as Record<string, unknown>).codeRepository).toBe('https://github.com/acme/kit')

    const noRepo = capabilityAppJsonLd({ slug: 's', name: 'n', kind: 'skill' })
    expect('codeRepository' in noRepo).toBe(false)
  })

  // D-07-05 REGRESSION GUARD: the score is an algorithmic audit, never user
  // reviews — Google manual-actions a fabricated AggregateRating/Review. The
  // builder must NEVER emit either key, with OR without a repoUrl.
  it('capabilityAppJsonLd NEVER emits aggregateRating / review (D-07-05)', () => {
    for (const kind of ['mcp_server', 'skill', 'hook', 'plugin', 'rules']) {
      for (const repoUrl of [undefined, 'https://github.com/a/b']) {
        const schema = capabilityAppJsonLd({ slug: 's', name: 'n', kind, repoUrl })
        const json = JSON.stringify(schema).toLowerCase()
        expect('aggregaterating' in (schema as Record<string, unknown>)).toBe(false)
        expect('review' in (schema as Record<string, unknown>)).toBe(false)
        expect(json).not.toContain('aggregaterating')
        expect(json).not.toContain('"review"')
        expect(json).not.toContain('ratingvalue')
      }
    }
  })

  it('breadcrumbJsonLd is a BreadcrumbList with 1-indexed positions + absolute items', () => {
    const b = breadcrumbJsonLd([
      { name: 'Capabilities', path: '/capabilities' },
      { name: 'Skills', path: '/capabilities?kind=skill' },
      { name: 'My Skill', path: '/items/acme--kit--skill-x' },
    ])
    expect(b['@type']).toBe('BreadcrumbList')
    const els = b.itemListElement as Array<Record<string, unknown>>
    expect(els).toHaveLength(3)
    expect(els.map((e) => e.position)).toEqual([1, 2, 3])
    expect(els[0]).toMatchObject({
      '@type': 'ListItem',
      position: 1,
      name: 'Capabilities',
      item: 'https://saferskills.ai/capabilities',
    })
    expect(els[2].item).toBe('https://saferskills.ai/items/acme--kit--skill-x')
  })

  it('datasetJsonLd is an Apache-2.0 Dataset with an Organization creator', () => {
    const d = datasetJsonLd({
      name: 'SaferSkills corpus',
      description: 'Open scan data.',
      url: 'https://saferskills.ai/research',
    })
    expect(d['@type']).toBe('Dataset')
    expect(d.license).toBe('https://www.apache.org/licenses/LICENSE-2.0')
    expect(d.creator).toMatchObject({ '@type': 'Organization', name: 'SaferSkills' })
  })

  // serializeJsonLd injects @context (builders return bare Things).
  it('serializeJsonLd injects @context on a single Thing', () => {
    const parsed = JSON.parse(serializeJsonLd(organizationJsonLd()))
    expect(parsed['@context']).toBe('https://schema.org')
    expect(parsed['@type']).toBe('Organization')
  })

  it('serializeJsonLd wraps an array into a single @graph', () => {
    const parsed = JSON.parse(
      serializeJsonLd([
        capabilityAppJsonLd({ slug: 's', name: 'n', kind: 'skill' }),
        breadcrumbJsonLd([{ name: 'Home', path: '/' }]),
      ])
    )
    expect(parsed['@context']).toBe('https://schema.org')
    expect(Array.isArray(parsed['@graph'])).toBe(true)
    expect(parsed['@graph']).toHaveLength(2)
    expect(parsed['@graph'][0]['@type']).toBe('SoftwareSourceCode')
    expect(parsed['@graph'][1]['@type']).toBe('BreadcrumbList')
  })
})
