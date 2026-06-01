import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { axe } from 'vitest-axe'
import Breadcrumb from '../../../components/atoms/Breadcrumb'

const ITEMS = [
  { label: 'Catalog', href: '/catalog' },
  { label: 'MCP Servers', href: '/catalog?kind=mcp_server' },
  { label: 'stripe-mcp', href: '/items/stripe--stripe-mcp' },
  { label: 'Respond' },
]

describe('Breadcrumb', () => {
  it('links every crumb except the last (current) one', () => {
    render(<Breadcrumb items={ITEMS} />)
    expect(screen.getByRole('link', { name: /Catalog/ })).toHaveAttribute('href', '/catalog')
    expect(screen.getByRole('link', { name: 'stripe-mcp' })).toHaveAttribute(
      'href',
      '/items/stripe--stripe-mcp',
    )
    // The final crumb is the current page — not a link.
    expect(screen.queryByRole('link', { name: 'Respond' })).not.toBeInTheDocument()
  })

  it('marks the final crumb as the current page', () => {
    render(<Breadcrumb items={ITEMS} />)
    const current = screen.getByText('Respond')
    expect(current).toHaveAttribute('aria-current', 'page')
  })

  it('is accessible (vitest-axe)', async () => {
    const { container } = render(<Breadcrumb items={ITEMS} />)
    const results = await axe(container)
    expect(results.violations).toHaveLength(0)
  })
})
