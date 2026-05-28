import { describe, expect, it } from 'vitest'
import { render } from '@testing-library/react'
import { axe } from 'vitest-axe'
import AgentMarquee from '../../../components/molecules/AgentMarquee'

describe('AgentMarquee', () => {
  it('duplicates the agent list for seamless looping (16 chips when 8 agents)', () => {
    const { container } = render(<AgentMarquee />)
    expect(container.querySelectorAll('.agent-chip').length).toBe(16)
  })

  it('is accessible (vitest-axe)', async () => {
    const { container } = render(<AgentMarquee />)
    const results = await axe(container)
    expect(results.violations).toHaveLength(0)
  })
})
