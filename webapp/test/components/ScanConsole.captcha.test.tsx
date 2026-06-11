import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

// Configure a Turnstile site key so the gate is active in this file's tests.
vi.mock('@/env', () => ({
  env: { PUBLIC_API_URL: 'http://localhost:8000', PUBLIC_TURNSTILE_SITE_KEY: '1x00AA' },
}))
vi.mock('@/lib/analytics', () => ({ track: vi.fn() }))
vi.mock('@/lib/api/scans', async (importActual) => {
  const actual = await importActual<typeof import('@/lib/api/scans')>()
  return { ...actual, submitUpload: vi.fn(), submitScan: vi.fn() }
})

// Controllable TurnstileGate stub: renders Verify/Cancel triggers when open so
// the host's open/verify/cancel + captcha-retry wiring can be driven directly.
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

import ScanConsole from '@/components/scan/ScanConsole'
import { submitUpload, UploadError } from '@/lib/api/scans'

function selectFile(name = 'SKILL.md') {
  const input = document.querySelector('input[type="file"]') as HTMLInputElement
  fireEvent.change(input, {
    target: { files: [new File(['# s'], name, { type: 'text/markdown' })] },
  })
}

describe('ScanConsole — Turnstile gate', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    window.matchMedia = vi.fn().mockReturnValue({
      matches: true,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    }) as unknown as typeof window.matchMedia
    Object.defineProperty(window, 'location', {
      value: { ...window.location, assign: vi.fn(), search: '', hash: '', pathname: '/scan' },
      writable: true,
    })
  })

  it('opens the gate instead of submitting when a site key is configured', () => {
    render(<ScanConsole />)
    selectFile()
    fireEvent.click(screen.getByRole('button', { name: /scan capability/i }))
    expect(screen.getByTestId('gate')).toBeTruthy()
    expect(submitUpload).not.toHaveBeenCalled()
  })

  it('submits with the verified captcha token on onVerified', async () => {
    vi.mocked(submitUpload).mockResolvedValue({
      id: 'r1',
      status: 'pending',
      source_kind: 'upload',
      visibility: 'public',
    })
    render(<ScanConsole />)
    selectFile()
    fireEvent.click(screen.getByRole('button', { name: /scan capability/i }))
    fireEvent.click(screen.getByRole('button', { name: 'verify' }))
    await waitFor(() => expect(submitUpload).toHaveBeenCalledTimes(1))
    const opts = vi.mocked(submitUpload).mock.calls[0][1]
    expect(opts.captchaToken).toBe('tok-1')
  })

  it('re-opens the gate on a 403 captcha_failed (single-use token consumed)', async () => {
    vi.mocked(submitUpload).mockRejectedValueOnce(new UploadError('captcha_failed', 403))
    render(<ScanConsole />)
    selectFile()
    fireEvent.click(screen.getByRole('button', { name: /scan capability/i }))
    fireEvent.click(screen.getByRole('button', { name: 'verify' }))
    await waitFor(() => expect(submitUpload).toHaveBeenCalledTimes(1))
    // onCaptchaRetry bounces the host back into a fresh gate rather than erroring.
    await waitFor(() => expect(screen.getByTestId('gate')).toBeTruthy())
  })
})
