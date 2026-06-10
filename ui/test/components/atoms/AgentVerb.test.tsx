import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { axe } from 'vitest-axe'
import AgentVerb from '../../../components/atoms/AgentVerb'

describe('AgentVerb', () => {
  it('maps each band to its verb', () => {
    const { rerender } = render(<AgentVerb band="red" />)
    expect(screen.getByText('Do-Not-Deploy')).toBeInTheDocument()
    rerender(<AgentVerb band="green" />)
    expect(screen.getByText('Ship')).toBeInTheDocument()
    rerender(<AgentVerb band="orange" />)
    expect(screen.getByText('Remediate')).toBeInTheDocument()
    rerender(<AgentVerb band="yellow" />)
    expect(screen.getByText('Review')).toBeInTheDocument()
  })

  it('renders an aria-hidden separator', () => {
    const { container } = render(<AgentVerb band="red" />)
    expect(container.querySelector('.vb-sep')?.getAttribute('aria-hidden')).toBe('true')
  })

  it('has no critical a11y violations', async () => {
    const { container } = render(<AgentVerb band="red" />)
    const results = await axe(container)
    expect(results.violations).toHaveLength(0)
  })
})
