import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { axe } from 'vitest-axe'

import CapabilityReportTabs from '@/components/scan/CapabilityReportTabs'
import { makeCapability } from '../factories/run-report'

describe('CapabilityReportTabs', () => {
  it('defaults to the Score breakdown tab and renders the 5 categories', () => {
    render(<CapabilityReportTabs cap={makeCapability()} manifest={null} />)
    expect(
      screen.getByRole('tab', { name: /score breakdown/i }).getAttribute('aria-selected')
    ).toBe('true')
    // The 5-axis breakdown (weights are unique to the category table).
    expect(screen.getByText('35%')).toBeTruthy() // security
    expect(screen.getByText('20%')).toBeTruthy() // supply_chain
    expect(screen.getByText(/findings & checks/i)).toBeTruthy()
    // Category name appears in both the weight table and the checks group.
    expect(screen.getAllByText('Security').length).toBeGreaterThan(0)
  })

  it('shows the source viewer when a manifest is present', () => {
    render(
      <CapabilityReportTabs
        cap={makeCapability()}
        manifest={{ path: 'SKILL.md', content: '# hello world', bytes: 2048 }}
      />
    )
    fireEvent.click(screen.getByRole('tab', { name: 'Source' }))
    expect(screen.getByText('SKILL.md')).toBeTruthy()
    // Raw tab exposes the verbatim content.
    fireEvent.click(screen.getByRole('button', { name: 'Raw' }))
    expect(screen.getByText('# hello world')).toBeTruthy()
  })

  it('degrades to a notice when no manifest was captured', () => {
    render(<CapabilityReportTabs cap={makeCapability()} manifest={null} />)
    fireEvent.click(screen.getByRole('tab', { name: 'Source' }))
    expect(screen.getByText(/source manifest not captured/i)).toBeTruthy()
  })

  it('is accessible (vitest-axe)', async () => {
    const { container } = render(
      <CapabilityReportTabs
        cap={makeCapability()}
        manifest={{ path: 'SKILL.md', content: '# hi', bytes: 1024 }}
      />
    )
    const results = await axe(container)
    expect(results.violations).toHaveLength(0)
  })
})
