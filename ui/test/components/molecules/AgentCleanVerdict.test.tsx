import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { axe } from 'vitest-axe'
import AgentCleanVerdict from '../../../components/molecules/AgentCleanVerdict'

describe('AgentCleanVerdict', () => {
  it('renders the verdict headline and the run-derived evidence ledger', () => {
    const { container } = render(
      <AgentCleanVerdict
        testsPassed={20}
        totalTests={20}
        familiesProbed={18}
        packLabel="saferskills-agent-baseline @ 2026.06.09"
      />
    )
    expect(screen.getByText('No findings.')).toBeInTheDocument()
    // ledger numbers come from props (tests passed · families · vulnerable)
    expect(container.querySelector('.cv-num')?.textContent).toContain('20')
    expect(screen.getByText('/20')).toBeInTheDocument()
    expect(screen.getByText('18')).toBeInTheDocument()
    expect(screen.getByText('Risk families probed')).toBeInTheDocument()
    // the reproducibility line carries the pack label
    expect(screen.getByText(/saferskills-agent-baseline @ 2026\.06\.09/)).toBeInTheDocument()
  })

  it('has no critical a11y violations', async () => {
    const { container } = render(
      <AgentCleanVerdict
        testsPassed={20}
        totalTests={20}
        familiesProbed={18}
        packLabel="saferskills-agent-baseline @ 2026.06.09"
      />
    )
    expect((await axe(container)).violations).toHaveLength(0)
  })
})
