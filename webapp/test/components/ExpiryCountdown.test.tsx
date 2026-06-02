import { render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import ExpiryCountdown from '@/components/scan/ExpiryCountdown'

describe('ExpiryCountdown', () => {
  afterEach(() => vi.useRealTimers())

  it('renders days when well out, as a pill', () => {
    const future = new Date(Date.now() + 89 * 86400_000).toISOString()
    render(<ExpiryCountdown expiresAt={future} variant="pill" />)
    const el = screen.getByText(/expires in 8\d days/i)
    expect(el.className).toContain('expiry-pill')
  })

  it('renders hours near the end', () => {
    const soon = new Date(Date.now() + 5 * 3600_000 + 30 * 60_000).toISOString()
    render(<ExpiryCountdown expiresAt={soon} />)
    expect(screen.getByText(/expires in 5 hours/i)).toBeTruthy()
  })

  it('shows Expired (defensive) for a past timestamp', () => {
    render(<ExpiryCountdown expiresAt={new Date(Date.now() - 1000).toISOString()} variant="pill" />)
    const el = screen.getByText('Expired')
    expect(el.className).toContain('expired')
  })

  it('renders nothing for an unparseable timestamp', () => {
    const { container } = render(<ExpiryCountdown expiresAt="not-a-date" />)
    expect(container.textContent).toBe('')
  })
})
