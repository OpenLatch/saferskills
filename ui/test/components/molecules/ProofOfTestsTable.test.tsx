import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { axe } from 'vitest-axe'
import ProofOfTestsTable, { type ProofCheck } from '../../../components/molecules/ProofOfTestsTable'

const CHECKS: ProofCheck[] = [
  { test_id: 'AS-01', family: 'Direct injection', title: 'Direct prompt injection', verdict: 'not_observed' },
  { test_id: 'AS-06', family: 'Tool-description poisoning', title: 'Hidden directive exfiltrated a secret', verdict: 'vulnerable' },
  { test_id: 'AS-09', family: 'Unsafe code execution', title: 'Executed an unsafe shell chain', verdict: 'vulnerable' },
  { test_id: 'AS-13', family: 'Confused deputy', title: 'Relayed a finance action', verdict: 'n_a' },
]

describe('ProofOfTestsTable', () => {
  it('shows the applied-tests header + passed count', () => {
    render(<ProofOfTestsTable checks={CHECKS} />)
    expect(screen.getByText('Rules & checks applied · 4 total')).toBeInTheDocument()
    // pass rows carry the PASS chip; vulnerable rows the View-finding button
    expect(screen.getAllByText('Pass')).toHaveLength(1)
    expect(screen.getAllByText('View finding →')).toHaveLength(2)
  })

  it('renders a View-finding button per vulnerable check and fires onViewFinding', () => {
    const onView = vi.fn()
    render(<ProofOfTestsTable checks={CHECKS} onViewFinding={onView} />)
    const buttons = screen.getAllByText('View finding →')
    expect(buttons).toHaveLength(2)
    fireEvent.click(buttons[0])
    expect(onView).toHaveBeenCalledWith('AS-06')
  })

  it('flips to the pass variant when nothing is vulnerable', () => {
    const clean = CHECKS.map((c) => ({ ...c, verdict: 'not_observed' as const }))
    const { container } = render(<ProofOfTestsTable checks={clean} />)
    expect(container.querySelector('.ar-tests.pass')).not.toBeNull()
    expect(screen.getAllByText('Pass')).toHaveLength(4)
    expect(screen.queryByText('View finding →')).toBeNull()
  })

  it('has no critical a11y violations', async () => {
    const { container } = render(<ProofOfTestsTable checks={CHECKS} />)
    const results = await axe(container)
    expect(results.violations).toHaveLength(0)
  })
})
