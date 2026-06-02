import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

vi.mock('@/lib/analytics', () => ({ track: vi.fn() }))

import ScanReportView from '@/components/scan/ScanReportView'
import { makeUnlistedGithubRun, makeUploadRun } from '../factories/run-report'

describe('ScanReportView — source + visibility aware (P0-9 / D-UP-33)', () => {
  it('renders an upload run without crashing on null github_url, evidence has no blob link', () => {
    render(<ScanReportView run={makeUploadRun()} shareUrl="https://saferskills.ai/scans/x" />)
    // Public upload keeps the catalog CTA + per-capability catalog link.
    expect(screen.getByText(/added to the public catalog/i)).toBeTruthy()
    expect(screen.getByRole('link', { name: /view in catalog/i })).toBeTruthy()
  })

  it('hides public-catalog copy + per-capability catalog links for an unlisted run', () => {
    render(
      <ScanReportView run={makeUnlistedGithubRun()} shareUrl="https://saferskills.ai/scans/r/t" />
    )
    expect(screen.queryByText(/added to the public catalog/i)).toBeNull()
    expect(screen.queryByRole('link', { name: /view in catalog/i })).toBeNull()
    // Replaced by the "stay private" framing + a private label per capability.
    expect(screen.getByText(/these capabilities stay private/i)).toBeTruthy()
    expect(screen.getAllByText('Private').length).toBeGreaterThan(0)
  })
})
