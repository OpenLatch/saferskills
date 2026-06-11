import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

// Turnstile site key configured — Copy opens the gate before minting.
vi.mock('@/env', () => ({
  env: { PUBLIC_API_URL: 'http://localhost:8000', PUBLIC_TURNSTILE_SITE_KEY: '1x00AA' },
}))
vi.mock('@/lib/analytics', () => ({ track: vi.fn() }))
vi.mock('@ui/components/atoms/Toast', () => ({
  default: () => null,
  flashToast: vi.fn(),
}))

// Controllable TurnstileGate stub — Verify/Cancel triggers drive the hook.
vi.mock('@ui/components/molecules/TurnstileGate', () => ({
  // biome-ignore lint/suspicious/noExplicitAny: minimal stub props
  default: ({ open, onVerified, onCancel }: any) =>
    open ? (
      <div data-testid="gate">
        <button type="button" onClick={() => onVerified('tok-1')}>
          verify
        </button>
        <button type="button" onClick={onCancel}>
          gate-cancel
        </button>
      </div>
    ) : null,
}))

import { flashToast } from '@ui/components/atoms/Toast'
import AgentScanHeroCard from '@/components/homepage/AgentScanHeroCard'

const writeText = vi.fn<(text: string) => Promise<void>>()

describe('AgentScanHeroCard — Turnstile gate (site key configured)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.unstubAllGlobals()
    writeText.mockResolvedValue(undefined)
    Object.defineProperty(navigator, 'clipboard', {
      value: { writeText },
      configurable: true,
    })
    window.matchMedia = vi.fn().mockReturnValue({
      matches: true,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    }) as unknown as typeof window.matchMedia
  })

  it('opens the gate instead of minting; verified token rides the header', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        status: 201,
        json: async () => ({ run_id: 'run-9', prompt: 'REAL' }),
      })
    )
    render(<AgentScanHeroCard />)
    fireEvent.click(screen.getByRole('button', { name: /^copy$/i }))
    // gate opens, nothing fetched/copied yet
    expect(screen.getByTestId('gate')).toBeTruthy()
    expect(fetch).not.toHaveBeenCalled()
    expect(writeText).not.toHaveBeenCalled()

    fireEvent.click(screen.getByRole('button', { name: 'verify' }))
    await waitFor(() => expect(writeText).toHaveBeenCalledWith('REAL'))
    const [, init] = vi.mocked(fetch).mock.calls[0] as [string, RequestInit]
    expect((init.headers as Record<string, string>)['Cf-Turnstile-Response']).toBe('tok-1')
  })

  it('gate cancel → back to idle, no fetch, no clipboard write', () => {
    vi.stubGlobal('fetch', vi.fn())
    render(<AgentScanHeroCard />)
    fireEvent.click(screen.getByRole('button', { name: /^copy$/i }))
    fireEvent.click(screen.getByRole('button', { name: 'gate-cancel' }))
    expect(screen.queryByTestId('gate')).toBeNull()
    expect(fetch).not.toHaveBeenCalled()
    expect(writeText).not.toHaveBeenCalled()
    expect(screen.getByRole('button', { name: /^copy$/i })).toBeTruthy()
  })

  it('403 captcha_failed reopens the gate ONCE, then toasts + idles', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        status: 403,
        json: async () => ({ error: 'captcha_failed' }),
      })
    )
    render(<AgentScanHeroCard />)
    fireEvent.click(screen.getByRole('button', { name: /^copy$/i }))
    fireEvent.click(screen.getByRole('button', { name: 'verify' }))
    // first 403 → a fresh gate reopens (single-use token consumed)
    await waitFor(() => expect(screen.getByTestId('gate')).toBeTruthy())
    expect(flashToast).not.toHaveBeenCalled()

    fireEvent.click(screen.getByRole('button', { name: 'verify' }))
    // second 403 → toast + idle, never copies the template
    await waitFor(() =>
      expect(flashToast).toHaveBeenCalledWith(expect.stringMatching(/verification failed/i))
    )
    expect(screen.queryByTestId('gate')).toBeNull()
    expect(writeText).not.toHaveBeenCalled()
    expect(vi.mocked(fetch)).toHaveBeenCalledTimes(2)
  })
})
