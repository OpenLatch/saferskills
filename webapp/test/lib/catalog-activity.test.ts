import { describe, expect, it } from 'vitest'
import { ACTIVITY_WEEKS, resolveActivity } from '../../src/lib/catalog-activity'

describe('resolveActivity', () => {
  it('uses real data when any week is non-zero', () => {
    const real = [0, 0, 3, 0, 1, 0, 0, 0, 0, 0, 0, 0, 2]
    const out = resolveActivity(real, 50)
    expect(out.placeholder).toBe(false)
    expect(out.values).toEqual(real)
  })

  it('falls back to a deterministic placeholder when empty', () => {
    const a = resolveActivity([0, 0, 0], 42, 'acme--kit--skill-x')
    const b = resolveActivity(null, 42, 'acme--kit--skill-x')
    expect(a.placeholder).toBe(true)
    expect(b.placeholder).toBe(true)
    expect(a.values).toHaveLength(ACTIVITY_WEEKS)
    // Deterministic: same popularity + same seedKey → identical placeholder series.
    expect(a.values).toEqual(b.values)
  })

  it('produces distinct shapes per row even at identical popularity', () => {
    // The visual bug this guards: same popularity (50) must NOT yield identical
    // sparklines — the slug seed makes each row distinct.
    const a = resolveActivity(undefined, 50, 'org--repo--skill-a')
    const b = resolveActivity(undefined, 50, 'org--repo--skill-b')
    expect(a.values).not.toEqual(b.values)
  })
})
