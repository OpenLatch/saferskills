import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { axe } from 'vitest-axe'
import Sparkline from '../../../components/atoms/Sparkline'

describe('Sparkline', () => {
  it('renders a line + area for a non-empty series', () => {
    const { container } = render(<Sparkline values={[0, 2, 1, 4, 3]} />)
    expect(container.querySelector('polyline.sparkline-line')).not.toBeNull()
    expect(container.querySelector('path.sparkline-area')).not.toBeNull()
    expect(container.querySelector('circle.sparkline-dot')).not.toBeNull()
  })

  it('summarizes the total in the aria-label', () => {
    render(<Sparkline values={[1, 2, 3]} />)
    expect(screen.getByRole('img', { name: /6 in the last quarter/i })).toBeTruthy()
  })

  it('reports an empty series as no activity', () => {
    render(<Sparkline values={[0, 0, 0]} />)
    expect(screen.getByRole('img', { name: /no recent install activity/i })).toBeTruthy()
  })

  it('applies the placeholder modifier class', () => {
    const { container } = render(<Sparkline values={[1, 2, 1]} placeholder />)
    expect(container.querySelector('svg.sparkline--placeholder')).not.toBeNull()
  })

  it('honours a custom aria-label', () => {
    render(<Sparkline values={[1]} ariaLabel="Custom trend" />)
    expect(screen.getByRole('img', { name: 'Custom trend' })).toBeTruthy()
  })

  it('is accessible (vitest-axe)', async () => {
    const { container } = render(<Sparkline values={[0, 3, 1, 5, 2]} />)
    const results = await axe(container)
    expect(results.violations).toHaveLength(0)
  })
})
