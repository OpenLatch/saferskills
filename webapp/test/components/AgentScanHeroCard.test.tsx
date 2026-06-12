import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

// No Turnstile site key in this file — the mint POSTs directly (dev path).
vi.mock('@/env', () => ({
  env: { PUBLIC_API_URL: 'http://localhost:8000', PUBLIC_TURNSTILE_SITE_KEY: undefined },
}))
vi.mock('@/lib/analytics', () => ({ track: vi.fn() }))
vi.mock('@ui/components/atoms/Toast', () => ({
  default: () => null,
  flashToast: vi.fn(),
}))

import { flashToast } from '@ui/components/atoms/Toast'
import AgentScanHeroCard from '@/components/homepage/AgentScanHeroCard'
import { track } from '@/lib/analytics'

const PROMPT = 'Run a **SaferSkills Agent Scan** on this agent.\nGET https://x/pack'

function mockMintOk() {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue({
      status: 201,
      json: async () => ({ run_id: 'run-1', prompt: PROMPT }),
    })
  )
}

function mockMintStatus(status: number, body: unknown = {}) {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ status, json: async () => body }))
}

const writeText = vi.fn<(text: string) => Promise<void>>()

describe('AgentScanHeroCard — inline mint state machine (no site key)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
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

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.useRealTimers()
  })

  it('shows the template preview with visible placeholders pre-mint', () => {
    render(<AgentScanHeroCard />)
    expect(screen.getAllByText(/\{\{PACK_URL\}\}/).length).toBeGreaterThan(0)
    expect(screen.getByText(/Scan an agent/).getAttribute('href')).toBe('/scan?mode=agent')
  })

  it('201 → clipboard gets the REAL prompt, foot swaps, telemetry fires once', async () => {
    mockMintOk()
    render(<AgentScanHeroCard />)
    fireEvent.click(screen.getByRole('button', { name: /^copy$/i }))
    await waitFor(() => expect(writeText).toHaveBeenCalledTimes(1))
    expect(writeText).toHaveBeenCalledWith(PROMPT)
    // body posts platform=universal + the toggle's visibility (default public)
    const [url, init] = vi.mocked(fetch).mock.calls[0] as [string, RequestInit]
    expect(url).toBe('http://localhost:8000/api/v1/agent-scans/bootstrap')
    expect(JSON.parse(init.body as string)).toEqual({
      platform: 'universal',
      visibility: 'public',
    })
    // no captcha header on the ungated path
    expect((init.headers as Record<string, string>)['Cf-Turnstile-Response']).toBeUndefined()
    // foot swap → the report link
    await waitFor(() => expect(screen.getByText(/your report will appear at/)).toBeTruthy())
    expect(screen.getByText(/your report will appear at/).getAttribute('href')).toBe(
      '/agents/run-1'
    )
    // telemetry exactly once, closed-enum props only
    expect(track).toHaveBeenCalledTimes(1)
    expect(track).toHaveBeenCalledWith('agent_scan_prompt_minted', {
      surface: 'homepage',
      visibility: 'public',
    })
  })

  it('mints with visibility=unlisted when the toggle is off', async () => {
    mockMintOk()
    render(<AgentScanHeroCard />)
    fireEvent.click(screen.getByRole('switch'))
    fireEvent.click(screen.getByRole('button', { name: /^copy$/i }))
    await waitFor(() => expect(writeText).toHaveBeenCalledTimes(1))
    const [, init] = vi.mocked(fetch).mock.calls[0] as [string, RequestInit]
    expect(JSON.parse(init.body as string).visibility).toBe('unlisted')
    expect(track).toHaveBeenCalledWith('agent_scan_prompt_minted', {
      surface: 'homepage',
      visibility: 'unlisted',
    })
  })

  it('resets the Copy button copied→idle after ~2s (the foot swap stays)', async () => {
    vi.useFakeTimers()
    mockMintOk()
    render(<AgentScanHeroCard />)
    fireEvent.click(screen.getByRole('button', { name: /^copy$/i }))
    // flush the fetch + clipboard microtasks under fake timers
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0)
    })
    expect(screen.getByRole('button', { name: /copied/i })).toBeTruthy()
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2100)
    })
    expect(screen.getByRole('button', { name: /^copy$/i })).toBeTruthy()
    // ready state persists — the foot still links to the report
    expect(screen.getByText(/your report will appear at/)).toBeTruthy()
  })

  it('429 → toast about the daily limit, NO clipboard write, back to idle', async () => {
    mockMintStatus(429)
    render(<AgentScanHeroCard />)
    fireEvent.click(screen.getByRole('button', { name: /^copy$/i }))
    await waitFor(() =>
      expect(flashToast).toHaveBeenCalledWith(expect.stringMatching(/daily agent-scan limit/i))
    )
    expect(writeText).not.toHaveBeenCalled()
    expect(track).not.toHaveBeenCalled()
    expect(screen.getByRole('button', { name: /^copy$/i })).toBeTruthy()
    // pre-mint foot is unchanged
    expect(screen.getByText(/Scan an agent/)).toBeTruthy()
  })

  it('403 without a site key → toast + idle (never copies the template)', async () => {
    mockMintStatus(403, { error: 'captcha_failed' })
    render(<AgentScanHeroCard />)
    fireEvent.click(screen.getByRole('button', { name: /^copy$/i }))
    await waitFor(() => expect(flashToast).toHaveBeenCalledTimes(1))
    expect(writeText).not.toHaveBeenCalled()
    expect(track).not.toHaveBeenCalled()
  })

  it('network failure → toast + idle, NO clipboard write', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('offline')))
    render(<AgentScanHeroCard />)
    fireEvent.click(screen.getByRole('button', { name: /^copy$/i }))
    await waitFor(() =>
      expect(flashToast).toHaveBeenCalledWith(expect.stringMatching(/network error/i))
    )
    expect(writeText).not.toHaveBeenCalled()
    expect(screen.getByRole('button', { name: /^copy$/i })).toBeTruthy()
  })

  it('clipboard blocked on 201 → ready (real prompt rendered) but NEVER claims "Copied"', async () => {
    mockMintOk()
    writeText.mockRejectedValue(new DOMException('denied', 'NotAllowedError'))
    render(<AgentScanHeroCard />)
    fireEvent.click(screen.getByRole('button', { name: /^copy$/i }))
    await waitFor(() =>
      expect(flashToast).toHaveBeenCalledWith(expect.stringMatching(/clipboard unavailable/i))
    )
    // mint succeeded → ready foot + real prompt rendered for manual copy
    expect(screen.getByText(/your report will appear at/)).toBeTruthy()
    // but the button must not lie about a copy that never happened
    expect(screen.queryByRole('button', { name: /copied/i })).toBeNull()
    expect(screen.getByRole('button', { name: /^copy$/i })).toBeTruthy()
    // the mint itself is still tracked (the run exists server-side)
    expect(track).toHaveBeenCalledTimes(1)
  })

  it('re-click after a mint re-copies the SAME prompt — no second POST, no telemetry re-fire', async () => {
    vi.useFakeTimers()
    mockMintOk()
    render(<AgentScanHeroCard />)
    fireEvent.click(screen.getByRole('button', { name: /^copy$/i }))
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0)
    })
    // wait out the copied→idle reset, then click again
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2100)
    })
    fireEvent.click(screen.getByRole('button', { name: /^copy$/i }))
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0)
    })
    expect(writeText).toHaveBeenCalledTimes(2)
    expect(writeText).toHaveBeenLastCalledWith(PROMPT)
    expect(vi.mocked(fetch)).toHaveBeenCalledTimes(1)
    expect(track).toHaveBeenCalledTimes(1)
  })

  it('unlisted mint → foot explains the private link, NO /agents/<run_id> anchor', async () => {
    mockMintOk()
    render(<AgentScanHeroCard />)
    fireEvent.click(screen.getByRole('switch'))
    fireEvent.click(screen.getByRole('button', { name: /^copy$/i }))
    await waitFor(() => expect(writeText).toHaveBeenCalledTimes(1))
    await waitFor(() => expect(screen.getByText(/private report link/i)).toBeTruthy())
    // the unlisted run would 404 on the public route — never link it
    expect(screen.queryByText(/your report will appear at/)).toBeNull()
    expect(document.querySelector('a[href="/agents/run-1"]')).toBeNull()
  })
})
