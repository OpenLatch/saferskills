import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { axe } from 'vitest-axe'
import StalePackBanner from '../../../components/atoms/StalePackBanner'

describe('StalePackBanner', () => {
  it('renders the message + a re-scan link', () => {
    render(<StalePackBanner text="pack v2 adds a test for your family — re-scan" rescanHref="/agents" />)
    expect(screen.getByText('pack v2 adds a test for your family — re-scan')).toBeInTheDocument()
    const cta = screen.getByText('Re-scan →') as HTMLAnchorElement
    expect(cta.getAttribute('href')).toBe('/agents')
  })

  it('is a status region', () => {
    const { container } = render(<StalePackBanner text="re-scan" />)
    expect(container.querySelector('[role="status"]')).not.toBeNull()
  })

  it('has no critical a11y violations', async () => {
    const { container } = render(<StalePackBanner text="re-scan" />)
    const results = await axe(container)
    expect(results.violations).toHaveLength(0)
  })
})
