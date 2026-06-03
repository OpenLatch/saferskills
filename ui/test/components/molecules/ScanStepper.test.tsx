import { render } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { axe } from 'vitest-axe'
import ScanStepper, { type ScanStep } from '../../../components/molecules/ScanStepper'

const STEPS: ScanStep[] = [
  { key: 'fetch', index: '01', name: 'Fetch', tag: 'clone', description: 'Clone the repo.', status: 'completed', fillPct: 100 },
  {
    key: 'security',
    index: '02',
    name: 'Security',
    tag: 'rules',
    description: 'Check for injection.',
    status: 'running',
    fillPct: 40,
    runningPct: 40,
  },
  { key: 'supply_chain', index: '03', name: 'Supply chain', tag: 'deps', description: 'Inspect deps.', status: 'pending' },
]

describe('ScanStepper', () => {
  it('renders step statuses, descriptions, and the running meta', () => {
    const { container, getByText } = render(
      <ScanStepper steps={STEPS} heading="Stages · 3" currentLabel="security" />
    )
    expect(container.querySelector('.scan-step.is-completed')).not.toBeNull()
    expect(container.querySelector('.scan-step.is-running')).not.toBeNull()
    expect(container.querySelector('.scan-step.is-pending')).not.toBeNull()
    expect(getByText('Clone the repo.')).toBeTruthy()
    expect(getByText(/running…\s*40%/)).toBeTruthy()
  })

  it('fills the connector for the running step', () => {
    const { container } = render(<ScanStepper steps={STEPS} />)
    const running = container.querySelector('.scan-step.is-running .scan-step-fill') as HTMLElement
    expect(running.style.height).toBe('40%')
  })

  it('is accessible (vitest-axe)', async () => {
    const { container } = render(<ScanStepper steps={STEPS} currentLabel="security" />)
    const results = await axe(container)
    expect(results.violations).toHaveLength(0)
  })
})
