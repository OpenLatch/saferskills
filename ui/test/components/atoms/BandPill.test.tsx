import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { axe } from 'vitest-axe'
import BandPill from '../../../components/atoms/BandPill'

describe('BandPill', () => {
  it('defaults the label to the tier name', () => {
    render(<BandPill tier="green" />)
    expect(screen.getByText('GREEN')).toBeInTheDocument()
  })

  it('respects an explicit label override', () => {
    render(<BandPill tier="red" label="failed" />)
    expect(screen.getByText('failed')).toBeInTheDocument()
  })

  it('is accessible across tiers (vitest-axe)', async () => {
    const { container } = render(
      <div>
        <BandPill tier="green" />
        <BandPill tier="yellow" />
        <BandPill tier="orange" />
        <BandPill tier="red" />
      </div>,
    )
    const results = await axe(container)
    expect(results.violations).toHaveLength(0)
  })
})
