import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { axe } from 'vitest-axe'
import RidgeRuler from '../../../components/atoms/RidgeRuler'

describe('RidgeRuler', () => {
  it('renders the label when provided', () => {
    render(<RidgeRuler label="— SCAN · 03 —" />)
    expect(screen.getByText(/SCAN · 03/)).toBeInTheDocument()
  })

  it('renders no label when omitted', () => {
    const { container } = render(<RidgeRuler />)
    expect(container.querySelector('.ridge-label')).toBeNull()
  })

  it('is accessible (vitest-axe)', async () => {
    const { container } = render(<RidgeRuler label="— SCAN · 03 —" />)
    const results = await axe(container)
    expect(results.violations).toHaveLength(0)
  })
})
