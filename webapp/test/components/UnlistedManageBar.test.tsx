import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

vi.mock('@/lib/api/scans', async (importActual) => {
  const actual = await importActual<typeof import('@/lib/api/scans')>()
  return { ...actual, promoteUnlisted: vi.fn(), deleteUnlisted: vi.fn() }
})
vi.mock('@/lib/analytics', () => ({ track: vi.fn() }))

import UnlistedManageBar from '@/components/scan/UnlistedManageBar'
import { track } from '@/lib/analytics'
import { deleteUnlisted, promoteUnlisted } from '@/lib/api/scans'

const SHARE = 'https://saferskills.ai/scans/r/secret-token-xyz'

beforeEach(() => {
  vi.clearAllMocks()
  // jsdom doesn't implement <dialog> modality — polyfill open/close.
  HTMLDialogElement.prototype.showModal = vi.fn(function (this: HTMLDialogElement) {
    this.open = true
  })
  HTMLDialogElement.prototype.close = vi.fn(function (this: HTMLDialogElement) {
    this.open = false
  })
  Object.assign(navigator, {
    clipboard: { writeText: vi.fn().mockResolvedValue(undefined) },
  })
  Object.defineProperty(window, 'location', {
    value: { ...window.location, assign: vi.fn() },
    writable: true,
  })
})

describe('UnlistedManageBar', () => {
  it('copies the share URL and fires a token-free analytics event', async () => {
    render(<UnlistedManageBar token="secret-token-xyz" shareUrl={SHARE} />)
    fireEvent.click(screen.getByRole('button', { name: /copy private link/i }))
    await waitFor(() => expect(navigator.clipboard.writeText).toHaveBeenCalledWith(SHARE))
    expect(track).toHaveBeenCalledWith('unlisted_manage_action', { action: 'copy_link' })
    // The analytics payload must never carry the token.
    expect(JSON.stringify(vi.mocked(track).mock.calls)).not.toContain('secret-token-xyz')
  })

  it('shows the same-token control warning inline', () => {
    render(<UnlistedManageBar token="t" shareUrl={SHARE} />)
    expect(screen.getByText(/anyone with this link can also delete or publish it/i)).toBeTruthy()
  })

  it('promote → confirm → navigates to the run report', async () => {
    vi.mocked(promoteUnlisted).mockResolvedValue({
      promoted: true,
      run_id: 'run-9',
      visibility: 'public',
      items: [],
    })
    render(<UnlistedManageBar token="t" shareUrl={SHARE} />)
    fireEvent.click(screen.getByRole('button', { name: /promote this scan to public/i }))
    fireEvent.click(screen.getByRole('button', { name: 'Publish permanently' }))
    await waitFor(() => expect(window.location.assign).toHaveBeenCalledWith('/scans/run-9'))
  })

  it('delete → confirm → navigates to /scan (token purged by leaving)', async () => {
    vi.mocked(deleteUnlisted).mockResolvedValue(undefined)
    render(<UnlistedManageBar token="t" shareUrl={SHARE} />)
    fireEvent.click(screen.getByRole('button', { name: /delete this scan/i }))
    fireEvent.click(screen.getByRole('button', { name: 'Delete permanently' }))
    await waitFor(() => expect(window.location.assign).toHaveBeenCalledWith('/scan?deleted=1'))
  })

  it('surfaces a GENERIC error on failure (no token-validity oracle)', async () => {
    vi.mocked(promoteUnlisted).mockRejectedValue(new Error('not_found'))
    render(<UnlistedManageBar token="t" shareUrl={SHARE} />)
    fireEvent.click(screen.getByRole('button', { name: /promote this scan to public/i }))
    fireEvent.click(screen.getByRole('button', { name: 'Publish permanently' }))
    // Both (closed) dialogs share the error state node in jsdom — assert at least one.
    const errs = await screen.findAllByText(/may have expired or been deleted/i)
    expect(errs.length).toBeGreaterThan(0)
    // Must not distinguish invalid vs expired vs deleted.
    expect(errs[0].textContent?.toLowerCase()).not.toContain('invalid')
  })

  it('is accessible (vitest-axe)', async () => {
    const { container } = render(<UnlistedManageBar token="t" shareUrl={SHARE} />)
    const results = await axe(container)
    expect(results.violations).toHaveLength(0)
  })
})
