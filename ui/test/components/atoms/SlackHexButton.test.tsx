import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { axe } from 'vitest-axe'
import SlackHexButton from '../../../components/atoms/SlackHexButton'

describe('SlackHexButton', () => {
  it('defaults to the /slack stable redirect', () => {
    render(<SlackHexButton />)
    expect(screen.getByRole('link')).toHaveAttribute('href', '/slack')
  })

  it('honors a custom href', () => {
    render(<SlackHexButton href="/community" />)
    expect(screen.getByRole('link')).toHaveAttribute('href', '/community')
  })

  it('exposes an accessible label', () => {
    render(<SlackHexButton />)
    expect(
      screen.getByRole('link', { name: 'Join our Slack community' }),
    ).toBeInTheDocument()
  })

  it('is accessible (vitest-axe)', async () => {
    const { container } = render(<SlackHexButton />)
    const results = await axe(container)
    expect(results.violations).toHaveLength(0)
  })
})
