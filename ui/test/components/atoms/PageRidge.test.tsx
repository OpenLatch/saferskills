import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { axe } from 'vitest-axe'
import PageRidge from '../../../components/atoms/PageRidge'

const VARIANTS = ['contour', 'mesh', 'swell', 'circuit'] as const

describe('PageRidge', () => {
  it.each(VARIANTS)('renders the %s variant with its class + an svg', (variant) => {
    const { container } = render(<PageRidge variant={variant} />)
    const ridge = container.querySelector('.ridge-header')
    expect(ridge).not.toBeNull()
    expect(ridge).toHaveClass(`ridge-${variant}`)
    expect(container.querySelector('svg')).not.toBeNull()
  })

  it('renders the label when provided', () => {
    render(<PageRidge variant="contour" label="— /ABOUT —" />)
    expect(screen.getByText(/\/ABOUT/)).toBeInTheDocument()
  })

  it('renders no label when omitted', () => {
    const { container } = render(<PageRidge variant="mesh" />)
    expect(container.querySelector('.ridge-label')).toBeNull()
  })

  it.each(VARIANTS)('is accessible — %s (vitest-axe)', async (variant) => {
    const { container } = render(<PageRidge variant={variant} label="— /PATH —" />)
    const results = await axe(container)
    expect(results.violations).toHaveLength(0)
  })
})
