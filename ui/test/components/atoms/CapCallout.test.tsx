import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { axe } from 'vitest-axe'
import CapCallout from '../../../components/atoms/CapCallout'

describe('CapCallout', () => {
  it('renders the callout text', () => {
    render(<CapCallout band="red" text="Capped to Red — 1 critical finding observed." />)
    expect(screen.getByText('Capped to Red — 1 critical finding observed.')).toBeInTheDocument()
  })

  it('shows a check glyph for a clean green band and a warning glyph otherwise', () => {
    const { container, rerender } = render(<CapCallout band="green" text="No cap applied." />)
    // check glyph = a single polyline path; warning glyph = a triangle + marks (3 paths)
    expect(container.querySelectorAll('.cr-ic path').length).toBe(1)
    rerender(<CapCallout band="red" text="Capped." />)
    expect(container.querySelectorAll('.cr-ic path').length).toBeGreaterThan(1)
  })

  it('has no critical a11y violations', async () => {
    const { container } = render(<CapCallout band="red" text="Capped to Red." />)
    const results = await axe(container)
    expect(results.violations).toHaveLength(0)
  })
})
