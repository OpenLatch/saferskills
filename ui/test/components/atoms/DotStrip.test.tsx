import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { axe } from 'vitest-axe'
import DotStrip from '../../../components/atoms/DotStrip'

describe('DotStrip', () => {
  it('renders 9 filled dots for value 87', () => {
    render(<DotStrip value={87} tier="green" />)
    const region = screen.getByLabelText(/score 87 of 100/i)
    expect(region.textContent?.replace(/\s+/g, '')).toBe('●●●●●●●●●○')
  })

  it('clamps values outside 0..100', () => {
    const { container } = render(<DotStrip value={-5} tier="red" />)
    const text = container.textContent?.replace(/\s+/g, '') ?? ''
    expect(text).toBe('○○○○○○○○○○')
  })

  it('is accessible (vitest-axe)', async () => {
    const { container } = render(<DotStrip value={72} tier="yellow" />)
    const results = await axe(container)
    expect(results.violations).toHaveLength(0)
  })
})
