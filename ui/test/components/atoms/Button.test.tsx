import { describe, expect, it, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { axe } from 'vitest-axe'
import Button from '../../../components/atoms/Button'

describe('Button', () => {
  it('renders children and triggers onClick', () => {
    const onClick = vi.fn()
    render(<Button onClick={onClick}>Submit scan</Button>)
    const btn = screen.getByRole('button', { name: /submit scan/i })
    expect(btn).toBeInTheDocument()
    fireEvent.click(btn)
    expect(onClick).toHaveBeenCalledOnce()
  })

  it('renders an anchor when `as="a"`', () => {
    render(<Button as="a" href="/catalog">Catalog</Button>)
    const link = screen.getByRole('link', { name: /catalog/i })
    expect(link).toHaveAttribute('href', '/catalog')
  })

  it('is accessible across variants (vitest-axe)', async () => {
    const { container } = render(
      <div>
        <Button>Default</Button>
        <Button variant="primary">Primary</Button>
        <Button variant="paper">Paper</Button>
        <Button variant="ghost">Ghost</Button>
      </div>,
    )
    const results = await axe(container)
    expect(results.violations).toHaveLength(0)
  })
})
