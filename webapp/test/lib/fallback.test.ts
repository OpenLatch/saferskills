import { describe, expect, it } from 'vitest'
import { fetchOrNull, pickCount, pickList } from '../../src/lib/fallback'
import { formatCount } from '../../src/lib/format'

describe('pickList', () => {
  const ph = ['p1', 'p2', 'p3']

  it('falls back when live has fewer than 3 items (boundary: 2 → placeholder)', () => {
    expect(pickList(['a', 'b'], ph)).toBe(ph)
  })

  it('uses live at the boundary (3 → live)', () => {
    const live = ['a', 'b', 'c']
    expect(pickList(live, ph)).toBe(live)
  })

  it('falls back on null / undefined', () => {
    expect(pickList(null, ph)).toBe(ph)
    expect(pickList(undefined, ph)).toBe(ph)
  })

  it('honours a custom minItems', () => {
    expect(pickList(['a'], ph, 1)).toEqual(['a'])
  })
})

describe('pickCount', () => {
  it('falls back below the floor (boundary: 9 → placeholder)', () => {
    expect(pickCount(9, 12_847)).toBe(12_847)
  })

  it('uses live at the floor (boundary: 10 → live)', () => {
    expect(pickCount(10, 12_847)).toBe(10)
  })

  it('falls back on null / undefined', () => {
    expect(pickCount(null, 42)).toBe(42)
    expect(pickCount(undefined, 42)).toBe(42)
  })

  it('honours a custom minCount (rule_count uses 1)', () => {
    expect(pickCount(55, 55, 1)).toBe(55)
    expect(pickCount(0, 55, 1)).toBe(55)
  })
})

describe('fetchOrNull', () => {
  it('returns the value on success', async () => {
    expect(await fetchOrNull(async () => 7)).toBe(7)
  })

  it('returns null when the fn throws', async () => {
    expect(
      await fetchOrNull(async () => {
        throw new Error('boom')
      })
    ).toBeNull()
  })
})

describe('formatCount', () => {
  it('thousands-separates', () => {
    expect(formatCount(12_847)).toBe('12,847')
    expect(formatCount(47)).toBe('47')
  })
})
