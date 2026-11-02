import { describe, expect, it } from 'vitest'
import { fetchOrNullWithin } from '@/lib/fallback'

describe('fetchOrNullWithin', () => {
  it('returns the value when the fetch beats the deadline', async () => {
    await expect(fetchOrNullWithin(async () => 'live', 1000)).resolves.toBe('live')
  })

  it('returns null at the deadline instead of waiting for a slow fetch', async () => {
    const never = () => new Promise<string>(() => {})
    await expect(fetchOrNullWithin(never, 5)).resolves.toBeNull()
  })

  it('returns null when the fetch fails', async () => {
    const failing = () => Promise.reject(new Error('API 503'))
    await expect(fetchOrNullWithin(failing, 1000)).resolves.toBeNull()
  })
})
