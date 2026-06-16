import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { axe } from 'vitest-axe'
import CapabilityStack from '../../../components/atoms/CapabilityStack'

describe('CapabilityStack', () => {
  it('renders a chip per non-zero kind with the count', () => {
    render(<CapabilityStack tally={{ skill: 2, mcp: 1, hook: 0, plugin: 0, rules: 0 }} />)
    expect(screen.getByText('2 Skill')).toBeInTheDocument()
    expect(screen.getByText('1 MCP')).toBeInTheDocument()
  })

  it('renders nothing when every kind is zero', () => {
    const { container } = render(
      <CapabilityStack tally={{ skill: 0, mcp: 0, hook: 0, plugin: 0, rules: 0 }} />
    )
    expect(container.firstChild).toBeNull()
  })

  it('has no critical a11y violations', async () => {
    const { container } = render(
      <CapabilityStack tally={{ skill: 1, mcp: 0, hook: 1, plugin: 0, rules: 0 }} />
    )
    const results = await axe(container)
    expect(results.violations).toHaveLength(0)
  })
})
