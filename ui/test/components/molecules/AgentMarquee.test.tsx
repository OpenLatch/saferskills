import { describe, expect, it } from 'vitest'
import { render } from '@testing-library/react'
import { axe } from 'vitest-axe'
import AgentMarquee from '../../../components/molecules/AgentMarquee'

describe('AgentMarquee', () => {
  it('repeats the agent list 4× for seamless looping (32 chips when 8 agents)', () => {
    const { container } = render(<AgentMarquee />)
    expect(container.querySelectorAll('.agent-chip').length).toBe(32)
  })

  it('renders an inline SVG logo for each chip', () => {
    const { container } = render(<AgentMarquee />)
    expect(container.querySelectorAll('.agent-chip svg.gly').length).toBe(32)
  })

  it('labels each chip with the agent name for screen readers', () => {
    const { getAllByLabelText } = render(<AgentMarquee />)
    expect(getAllByLabelText('Claude Code').length).toBe(4)
    expect(getAllByLabelText('Gemini CLI').length).toBe(4)
  })

  it('falls back to an initials chip when no logo is registered', () => {
    const { container } = render(
      <AgentMarquee agents={[{ id: 'unknown-agent', name: 'Unknown', glyph: 'UN' }]} />,
    )
    expect(container.querySelectorAll('.agent-chip').length).toBe(4)
    expect(container.querySelectorAll('.agent-chip .gly-text').length).toBe(4)
    expect(container.querySelectorAll('.agent-chip svg.gly').length).toBe(0)
  })

  it('is accessible (vitest-axe)', async () => {
    const { container } = render(<AgentMarquee />)
    const results = await axe(container)
    expect(results.violations).toHaveLength(0)
  })
})
