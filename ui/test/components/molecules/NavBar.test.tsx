import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { axe } from 'vitest-axe'
import NavBar from '../../../components/molecules/NavBar'

describe('NavBar', () => {
  it('renders the default 5 links', () => {
    render(<NavBar />)
    expect(screen.getByRole('link', { name: 'Home' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Catalog' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Scan' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Docs' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Methodology' })).toBeInTheDocument()
  })

  it('renders the GhStar when count > 0', () => {
    render(<NavBar ghCount={26908} />)
    expect(screen.getByRole('link', { name: /Star.*GitHub/i })).toBeInTheDocument()
  })

  it('is accessible (vitest-axe)', async () => {
    const { container } = render(<NavBar ghCount={42} />)
    const results = await axe(container)
    expect(results.violations).toHaveLength(0)
  })
})
