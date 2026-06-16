import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

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
import AgentScanActivation from '@/components/scan/AgentScanActivation'
import { track } from '@/lib/analytics'

const PROMPT = 'Run a **SaferSkills Agent Scan** on this agent.\nGET https://x/pack'

function mockMintOk() {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue({
      status: 201,
      json: async () => ({ run_id: 'run-7', prompt: PROMPT }),
    })
  )
}

function mockMintStatus(status: number, body: unknown = {}) {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ status, json: async () => body }))
}

const writeText = vi.fn<(text: string) => Promise<void>>()

function generateBtn() {
  return screen.getByRole('button', { name: /generate my scan prompt/i })
}

describe('AgentScanActivation — platform picker + mint (no site key)', () => {
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

  it('picker surface — pre-mint: template, Universal selected, its hint shown', () => {
    render(<AgentScanActivation surface="picker" />)
    expect(screen.getAllByText(/\{\{PACK_URL\}\}/).length).toBeGreaterThan(0)
    const universal = screen.getByRole('button', { name: 'Universal' })
    expect(universal.getAttribute('aria-pressed')).toBe('true')
    expect(screen.getByText(/paste into your agent's chat/i)).toBeTruthy()
    // role="group", NOT a tablist (a selection over one prompt block).
    expect(screen.getByRole('group', { name: /agent platform/i })).toBeTruthy()
    expect(screen.queryByRole('tablist')).toBeNull()
  })

  it('scan surface — NO platform picker or hint, but the template + generate action render', () => {
    render(<AgentScanActivation surface="scan" />)
    // The picker + per-platform hint are picker-page-only (omitted on /scan).
    expect(screen.queryByRole('group', { name: /agent platform/i })).toBeNull()
    expect(screen.queryByRole('button', { name: 'Universal' })).toBeNull()
    expect(screen.queryByText(/paste into your agent's chat/i)).toBeNull()
    // The universal template + the mint action are still present.
    expect(screen.getAllByText(/\{\{PACK_URL\}\}/).length).toBeGreaterThan(0)
    expect(generateBtn()).toBeTruthy()
  })

  it('platform selection flows into the mint payload + swaps the hint line', async () => {
    mockMintOk()
    render(<AgentScanActivation surface="picker" />)
    fireEvent.click(screen.getByRole('button', { name: 'Codex CLI' }))
    expect(screen.getByText(/paste into codex/i)).toBeTruthy()
    fireEvent.click(generateBtn())
    await waitFor(() => expect(writeText).toHaveBeenCalledTimes(1))
    const [url, init] = vi.mocked(fetch).mock.calls[0] as [string, RequestInit]
    expect(url).toBe('http://localhost:8000/api/v1/agent-scans/bootstrap')
    expect(JSON.parse(init.body as string)).toEqual({ platform: 'codex', visibility: 'public' })
  })

  it('201 → substituted prompt rendered + copied, foot links the report, telemetry fires once with the surface', async () => {
    mockMintOk()
    render(<AgentScanActivation surface="picker" />)
    fireEvent.click(generateBtn())
    await waitFor(() => expect(writeText).toHaveBeenCalledWith(PROMPT))
    // The card now renders the REAL prompt — no placeholders left.
    expect(screen.queryByText(/\{\{PACK_URL\}\}/)).toBeNull()
    expect(screen.getByText(/your report will appear at/i).getAttribute('href')).toBe(
      '/agents/run-7'
    )
    // post-mint actions swap in
    expect(screen.getByRole('button', { name: /copy & paste into your agent/i })).toBeTruthy()
    expect(screen.getByRole('button', { name: /generate a new prompt/i })).toBeTruthy()
    expect(track).toHaveBeenCalledTimes(1)
    expect(track).toHaveBeenCalledWith('agent_scan_prompt_minted', {
      surface: 'picker',
      visibility: 'public',
    })
  })

  it('unlisted mint → private-link foot, NO /agents/<run_id> anchor', async () => {
    mockMintOk()
    render(<AgentScanActivation surface="scan" />)
    fireEvent.click(screen.getByRole('switch', { name: /make results public/i }))
    fireEvent.click(generateBtn())
    await waitFor(() => expect(screen.getByText(/private report link/i)).toBeTruthy())
    expect(screen.queryByText(/your report will appear at/i)).toBeNull()
    expect(document.querySelector('a[href="/agents/run-7"]')).toBeNull()
    const [, init] = vi.mocked(fetch).mock.calls[0] as [string, RequestInit]
    expect(JSON.parse(init.body as string).visibility).toBe('unlisted')
  })

  it('429 → toast + reset to pre-mint, template NEVER copied', async () => {
    mockMintStatus(429)
    render(<AgentScanActivation surface="scan" />)
    fireEvent.click(generateBtn())
    await waitFor(() =>
      expect(flashToast).toHaveBeenCalledWith(expect.stringMatching(/daily agent-scan limit/i))
    )
    expect(writeText).not.toHaveBeenCalled()
    expect(track).not.toHaveBeenCalled()
    // back to pre-mint: the Generate action + the template placeholders
    expect(generateBtn()).toBeTruthy()
    expect(screen.getAllByText(/\{\{PACK_URL\}\}/).length).toBeGreaterThan(0)
  })

  it('403 without a site key → toast + reset to pre-mint, template NEVER copied', async () => {
    mockMintStatus(403, { error: 'captcha_failed' })
    render(<AgentScanActivation surface="scan" />)
    fireEvent.click(generateBtn())
    await waitFor(() => expect(flashToast).toHaveBeenCalledTimes(1))
    expect(writeText).not.toHaveBeenCalled()
    expect(track).not.toHaveBeenCalled()
    expect(generateBtn()).toBeTruthy()
  })

  it('"Generate a new prompt" resets to the template; a re-generate POSTs a fresh run', async () => {
    mockMintOk()
    render(<AgentScanActivation surface="scan" />)
    fireEvent.click(generateBtn())
    await waitFor(() => expect(writeText).toHaveBeenCalledTimes(1))
    fireEvent.click(screen.getByRole('button', { name: /generate a new prompt/i }))
    // back to the pre-mint state — template visible, foot gone
    expect(screen.getAllByText(/\{\{PACK_URL\}\}/).length).toBeGreaterThan(0)
    expect(screen.queryByText(/your report will appear at/i)).toBeNull()
    // and a fresh mint actually re-POSTs (no stale ready short-circuit)
    fireEvent.click(generateBtn())
    await waitFor(() => expect(vi.mocked(fetch)).toHaveBeenCalledTimes(2))
    expect(track).toHaveBeenCalledTimes(2)
  })

  it('post-mint "Copy & paste into your agent" re-copies WITHOUT a second POST', async () => {
    mockMintOk()
    render(<AgentScanActivation surface="scan" />)
    fireEvent.click(generateBtn())
    await waitFor(() => expect(writeText).toHaveBeenCalledTimes(1))
    // post-mint action present + clickable (copyState 'copied' ≠ 'busy')
    fireEvent.click(screen.getByRole('button', { name: /copy & paste into your agent/i }))
    await waitFor(() => expect(writeText).toHaveBeenCalledTimes(2))
    expect(writeText).toHaveBeenLastCalledWith(PROMPT)
    expect(vi.mocked(fetch)).toHaveBeenCalledTimes(1)
    expect(track).toHaveBeenCalledTimes(1)
  })

  it('locks the platform picker while a minted prompt is live; reset unlocks it', async () => {
    mockMintOk()
    render(<AgentScanActivation surface="picker" />)
    fireEvent.click(generateBtn())
    await waitFor(() => expect(writeText).toHaveBeenCalledTimes(1))
    // every non-selected platform is disabled — the chip/hint can never
    // disagree with what a re-copy puts in the clipboard
    const cursorBtn = screen.getByRole('button', { name: 'Cursor' })
    expect(cursorBtn.hasAttribute('disabled')).toBe(true)
    fireEvent.click(cursorBtn)
    expect(screen.getByRole('button', { name: 'Universal' }).getAttribute('aria-pressed')).toBe(
      'true'
    )
    // "Generate a new prompt" unlocks the picker
    fireEvent.click(screen.getByRole('button', { name: /generate a new prompt/i }))
    expect(screen.getByRole('button', { name: 'Cursor' }).hasAttribute('disabled')).toBe(false)
  })
})
