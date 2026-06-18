import { describe, expect, it } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { axe } from 'vitest-axe'
import NavBar from '../../../components/molecules/NavBar'

describe('NavBar', () => {
  it('renders the default 6 links', () => {
    render(<NavBar />)
    // The mobile drawer duplicates these links but is `hidden` while closed,
    // so each accessible link resolves uniquely.
    expect(screen.getByRole('link', { name: 'Home' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Capabilities' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Agents' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Scan' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Docs' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Methodology' })).toBeInTheDocument()
  })

  it('renders the GhStar with a count', () => {
    render(<NavBar ghCount={26908} />)
    expect(screen.getByRole('link', { name: /Star.*GitHub/i })).toBeInTheDocument()
    // Desktop + (hidden) drawer each render the chip.
    expect(screen.getAllByText('26.9k')).toHaveLength(2)
  })

  // Regression: the GhStar must appear on EVERY page even when the route does
  // not pass a count (the count is filled live by NavStars). Previously the
  // NavBar gated it on `ghCount > 0`, so /items/<slug> + /respond (which pass no
  // count) silently dropped the GitHub-star CTA from the top bar.
  it('always renders the GhStar even with no ghCount', () => {
    render(<NavBar />)
    expect(screen.getByRole('link', { name: /Star.*GitHub/i })).toBeInTheDocument()
  })

  it('renders the Slack community chip defaulting to /slack', () => {
    render(<NavBar />)
    // The closed drawer is `hidden` (out of the a11y tree), so the visible
    // desktop chip resolves uniquely — same pattern as the GhStar assertions.
    expect(screen.getByRole('link', { name: 'Join our Slack community' })).toHaveAttribute(
      'href',
      '/slack',
    )
  })

  it('honors a custom slackHref', () => {
    render(<NavBar slackHref="/community" />)
    expect(screen.getByRole('link', { name: 'Join our Slack community' })).toHaveAttribute(
      'href',
      '/community',
    )
  })

  it('marks the active link from activePath (SSR-safe, no window read)', () => {
    render(<NavBar activePath="/capabilities" />)
    expect(screen.getByRole('link', { name: 'Capabilities' })).toHaveAttribute(
      'aria-current',
      'page',
    )
    expect(screen.getByRole('link', { name: 'Home' })).not.toHaveAttribute('aria-current')
  })

  it('toggles the mobile drawer open and closed via the hamburger', () => {
    render(<NavBar ghCount={42} />)
    const toggle = screen.getByRole('button', { name: 'Open menu' })
    expect(toggle).toHaveAttribute('aria-expanded', 'false')
    // Closed: drawer is hidden, so only the one desktop copy of each link exists.
    expect(screen.getAllByRole('link', { name: 'Home' })).toHaveLength(1)

    fireEvent.click(toggle)
    expect(toggle).toHaveAttribute('aria-expanded', 'true')
    expect(toggle).toHaveAccessibleName('Close menu')
    // Open: the drawer copy is now exposed alongside the desktop copy.
    expect(screen.getAllByRole('link', { name: 'Home' })).toHaveLength(2)

    fireEvent.click(toggle)
    expect(toggle).toHaveAttribute('aria-expanded', 'false')
    expect(screen.getAllByRole('link', { name: 'Home' })).toHaveLength(1)
  })

  it('closes the drawer on Escape', () => {
    render(<NavBar />)
    const toggle = screen.getByRole('button', { name: 'Open menu' })
    fireEvent.click(toggle)
    expect(toggle).toHaveAttribute('aria-expanded', 'true')
    fireEvent.keyDown(window, { key: 'Escape' })
    expect(toggle).toHaveAttribute('aria-expanded', 'false')
  })

  it('is accessible (vitest-axe)', async () => {
    const { container } = render(<NavBar ghCount={42} />)
    const results = await axe(container)
    expect(results.violations).toHaveLength(0)
  })
})
