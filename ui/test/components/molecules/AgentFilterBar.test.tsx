import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { axe } from 'vitest-axe'
import AgentFilterBar, { DEFAULT_AGENT_FILTERS } from '../../../components/molecules/AgentFilterBar'

describe('AgentFilterBar', () => {
  it('renders the search, the three multiselects, and the sort control', () => {
    render(<AgentFilterBar value={DEFAULT_AGENT_FILTERS} onChange={() => {}} />)
    expect(screen.getByLabelText('Search assessed agents')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Filter by time period' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Filter by agent runtime' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Filter by findings severity' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Sort agents/ })).toBeInTheDocument()
  })

  it('patches the query on search input', () => {
    const onChange = vi.fn()
    render(<AgentFilterBar value={DEFAULT_AGENT_FILTERS} onChange={onChange} />)
    fireEvent.change(screen.getByLabelText('Search assessed agents'), {
      target: { value: 'acme' },
    })
    expect(onChange).toHaveBeenCalledWith({ q: 'acme' })
  })

  it('has no critical a11y violations', async () => {
    const { container } = render(<AgentFilterBar value={DEFAULT_AGENT_FILTERS} onChange={() => {}} />)
    const results = await axe(container)
    expect(results.violations).toHaveLength(0)
  })
})
