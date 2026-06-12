import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

// Keep UploadError real (instanceof checks); mock the network calls.
vi.mock('@/lib/api/scans', async (importActual) => {
  const actual = await importActual<typeof import('@/lib/api/scans')>()
  return { ...actual, submitUpload: vi.fn(), submitScan: vi.fn() }
})
vi.mock('@/lib/analytics', () => ({ track: vi.fn() }))

import ScanConsole from '@/components/scan/ScanConsole'
import { submitScan, submitUpload, UploadError } from '@/lib/api/scans'

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

  it('renders the v3 single pane — drop zone + URL input + public toggle + consent', () => {
    render(<ScanConsole />)
    // Both inputs visible at once (the "or paste a URL" divider layout).
    expect(document.querySelector('input[type="file"]')).toBeTruthy()
    expect(screen.getByLabelText(/github repository to scan/i)).toBeTruthy()
    expect(screen.getByText(/or paste a URL/i)).toBeTruthy()
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

  it('uploads a selected file and navigates to the run report', async () => {
    vi.mocked(submitUpload).mockResolvedValue({
      id: 'run-1',
      status: 'pending',
      source_kind: 'upload',
      visibility: 'public',
    })
    render(<ScanConsole />)
    selectFile()
    fireEvent.click(screen.getByRole('button', { name: /scan capability/i }))
    await waitFor(() => expect(submitUpload).toHaveBeenCalledTimes(1))
    await waitFor(() => expect(window.location.assign).toHaveBeenCalledWith('/scans/run-1'))
  })

  it('renders the bucketed error when the upload is rejected', async () => {
    vi.mocked(submitUpload).mockRejectedValue(new UploadError('upload_too_large', 413))
    render(<ScanConsole />)
    selectFile()
    fireEvent.click(screen.getByRole('button', { name: /scan capability/i }))
    await waitFor(() =>
      expect(screen.getAllByText(/larger than the 10 MiB limit/i).length).toBeGreaterThan(0)
    )
  })

  it('files selected AND a URL typed → the URL-side submit forces the url path', async () => {
    vi.mocked(submitScan).mockResolvedValue({ run_id: 'run-9' } as never)
    render(<ScanConsole />)
    selectFile()
    const urlInput = screen.getByLabelText(/github repository to scan/i)
    fireEvent.change(urlInput, { target: { value: 'github.com/acme/linear-mcp' } })
    // The URL field's own ↵ button must submit the URL, not the picked files
    // (the old Upload/Scan-repo tabs let the user choose — this preserves it).
    fireEvent.click(screen.getByRole('button', { name: /scan repository/i }))
    await waitFor(() => expect(submitScan).toHaveBeenCalledTimes(1))
    expect(submitUpload).not.toHaveBeenCalled()
  })
})
