import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { axe } from 'vitest-axe'
import Badge from '../../../components/atoms/Badge'

describe('Badge', () => {
  it('renders the label', () => {
    render(<Badge>INDEXED</Badge>)
    expect(screen.getByText('INDEXED')).toBeInTheDocument()
  })

  it('shows the pulse dot when variant=live', () => {
    const { container } = render(<Badge variant="live">LIVE</Badge>)
    expect(container.querySelector('.badge.live')).not.toBeNull()
    expect(container.querySelector('.badge.live .dot')).not.toBeNull()
  })

  it('is accessible (vitest-axe)', async () => {
    const { container } = render(
      <div>
        <Badge>INDEXED</Badge>
        <Badge variant="live">LIVE</Badge>
      </div>,
    )
    const results = await axe(container)
    expect(results.violations).toHaveLength(0)
  })
})
