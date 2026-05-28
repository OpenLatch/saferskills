import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { axe } from 'vitest-axe'
import RidgeStars from '../../../components/atoms/RidgeStars'

describe('RidgeStars', () => {
  it('renders the label when provided', () => {
    render(<RidgeStars label="— FEEDS · 04 —" />)
    expect(screen.getByText(/FEEDS · 04/)).toBeInTheDocument()
  })

  it('renders no label when omitted', () => {
    const { container } = render(<RidgeStars />)
    expect(container.querySelector('.ridge-label')).toBeNull()
  })

  it('is accessible (vitest-axe)', async () => {
    const { container } = render(<RidgeStars label="— WHY ——" />)
    const results = await axe(container)
    expect(results.violations).toHaveLength(0)
  })
})
