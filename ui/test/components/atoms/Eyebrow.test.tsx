import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { axe } from 'vitest-axe'
import Eyebrow from '../../../components/atoms/Eyebrow'

describe('Eyebrow', () => {
  it('renders the children', () => {
    render(<Eyebrow>FEEDS · 04</Eyebrow>)
    expect(screen.getByText(/FEEDS · 04/)).toBeInTheDocument()
  })

  it('adds the no-rule class when withRule=false', () => {
    const { container } = render(<Eyebrow withRule={false}>X</Eyebrow>)
    expect(container.querySelector('.eyebrow.no-rule')).not.toBeNull()
  })

  it('is accessible (vitest-axe)', async () => {
    const { container } = render(<Eyebrow>SCORES · 5</Eyebrow>)
    const results = await axe(container)
    expect(results.violations).toHaveLength(0)
  })
})
