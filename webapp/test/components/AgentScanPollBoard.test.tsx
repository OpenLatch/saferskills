import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import AgentScanPollBoard from '@/components/agent/AgentScanPollBoard'

// The board polls on an interval; stub the fetch helpers so no real network +
// the run never becomes reportable (so it never reloads under test).
vi.mock('@/lib/api/agent-scans', () => ({
  fetchAgentScanRunById: vi.fn().mockResolvedValue(null),
  fetchAgentScanUnlistedReport: vi.fn().mockResolvedValue({ status: 'not_found' }),
}))

describe('AgentScanPollBoard', () => {
  it('renders the auditing board for a public run', () => {
    render(<AgentScanPollBoard runId="r1" target="acme-coding-agent" ruleCount={42} />)
    expect(screen.getByText('Auditing acme-coding-agent…')).toBeTruthy()
    expect(screen.getByText('auditing')).toBeTruthy()
  })

  it('is a polite, busy live region', () => {
    const { container } = render(<AgentScanPollBoard token="tok" target="acme" ruleCount={1} />)
    const region = container.querySelector('[aria-live="polite"]')
    expect(region?.getAttribute('aria-busy')).toBe('true')
  })
})
