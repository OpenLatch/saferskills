import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { axe } from 'vitest-axe'
import BracketLabel from '../../../components/atoms/BracketLabel'

describe('BracketLabel', () => {
  it('renders the label', () => {
    render(<BracketLabel>section · 03</BracketLabel>)
    expect(screen.getByText('section · 03')).toBeInTheDocument()
  })

  it('is accessible (vitest-axe)', async () => {
    const { container } = render(<BracketLabel>scope</BracketLabel>)
    const results = await axe(container)
    expect(results.violations).toHaveLength(0)
  })
})
