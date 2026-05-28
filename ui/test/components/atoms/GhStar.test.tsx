import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { axe } from 'vitest-axe'
import GhStar from '../../../components/atoms/GhStar'

describe('GhStar', () => {
  it('renders the count with k-suffix shortening for >=1000', () => {
    render(<GhStar count={26908} />)
    expect(screen.getByText('26.9k')).toBeInTheDocument()
  })

  it('renders raw count for <1000', () => {
    render(<GhStar count={847} />)
    expect(screen.getByText('847')).toBeInTheDocument()
  })

  it('links to the repo with rel=noopener', () => {
    render(<GhStar count={42} repo="OpenLatch/saferskills" />)
    const link = screen.getByRole('link')
    expect(link).toHaveAttribute('href', 'https://github.com/OpenLatch/saferskills')
    expect(link).toHaveAttribute('rel', 'noopener')
  })

  it('is accessible (vitest-axe)', async () => {
    const { container } = render(<GhStar count={26908} />)
    const results = await axe(container)
    expect(results.violations).toHaveLength(0)
  })
})
