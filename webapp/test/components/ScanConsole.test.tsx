import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

// Keep UploadError real (instanceof checks); mock the network calls.
vi.mock('@/lib/api/scans', async (importActual) => {
  const actual = await importActual<typeof import('@/lib/api/scans')>()
  return { ...actual, submitUpload: vi.fn(), submitScan: vi.fn() }
})
vi.mock('@/lib/analytics', () => ({ track: vi.fn() }))
vi.mock('@/lib/upload-handoff', () => ({ takePendingUpload: vi.fn().mockResolvedValue(null) }))

import ScanConsole from '@/components/scan/ScanConsole'
import { submitUpload, UploadError } from '@/lib/api/scans'

function makeFile(name = 'SKILL.md') {
  return new File(['# skill'], name, { type: 'text/markdown' })
}

function selectFile(name = 'SKILL.md') {
  const input = document.querySelector('input[type="file"]') as HTMLInputElement
  fireEvent.change(input, { target: { files: [makeFile(name)] } })
}

describe('ScanConsole', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    window.matchMedia = vi.fn().mockReturnValue({
      matches: true, // reduced-motion → navigate immediately (no timer)
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    }) as unknown as typeof window.matchMedia
    Object.defineProperty(window, 'location', {
      value: { ...window.location, assign: vi.fn(), search: '', hash: '', pathname: '/scan' },
      writable: true,
    })
  })

  it('defaults to the Upload tab with a public toggle + passive consent', () => {
    render(<ScanConsole />)
    expect(screen.getByRole('tab', { name: 'Upload' }).getAttribute('aria-selected')).toBe('true')
    expect(
      screen.getByRole('switch', { name: /make results public/i }).getAttribute('aria-checked')
    ).toBe('true')
    expect(screen.getByText(/published permanently/i)).toBeTruthy()
  })

  it('reveals the unlisted note when toggled private', () => {
    render(<ScanConsole />)
    fireEvent.click(screen.getByRole('switch', { name: /make results public/i }))
    expect(screen.getByText(/anyone with the link can see it/i)).toBeTruthy()
  })

  it('switches to the Scan-repo tab and shows the GitHub input', () => {
    render(<ScanConsole />)
    fireEvent.click(screen.getByRole('tab', { name: 'Scan repo' }))
    expect(screen.getByLabelText(/github repository to scan/i)).toBeTruthy()
  })

  it('uploads a selected file and navigates to the run report', async () => {
    vi.mocked(submitUpload).mockResolvedValue({
      id: 'run-1',
      status: 'pending',
      source_kind: 'upload',
      visibility: 'public',
    })
    render(<ScanConsole />)
    selectFile()
    fireEvent.click(screen.getByRole('button', { name: /scan now/i }))
    await waitFor(() => expect(submitUpload).toHaveBeenCalledTimes(1))
    await waitFor(() => expect(window.location.assign).toHaveBeenCalledWith('/scans/run-1'))
  })

  it('renders the bucketed error when the upload is rejected', async () => {
    vi.mocked(submitUpload).mockRejectedValue(new UploadError('upload_too_large', 413))
    render(<ScanConsole />)
    selectFile()
    fireEvent.click(screen.getByRole('button', { name: /scan now/i }))
    await waitFor(() =>
      expect(screen.getAllByText(/larger than the 10 MiB limit/i).length).toBeGreaterThan(0)
    )
  })
})
