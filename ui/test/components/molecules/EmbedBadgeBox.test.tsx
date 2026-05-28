import { describe, expect, it } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { axe } from 'vitest-axe'
import EmbedBadgeBox from '../../../components/molecules/EmbedBadgeBox'

describe('EmbedBadgeBox', () => {
  it('renders the markdown snippet by default', () => {
    const { container } = render(<EmbedBadgeBox scanId="abc123" score={87} slug="acme--foo" />)
    expect(container.querySelector('code')?.textContent).toContain('SaferSkills 87/100')
    expect(container.querySelector('code')?.textContent).toContain('badge/abc123/87.svg')
  })

  it('switches to html snippet when the HTML tab is clicked', () => {
    const { container } = render(<EmbedBadgeBox scanId="abc123" score={87} slug="acme--foo" />)
    const tabs = container.querySelectorAll('.embed-badge-box-tab')
    fireEvent.click(tabs[1])
    expect(screen.getByRole('tab', { name: /html/i }).getAttribute('aria-selected')).toBe('true')
    expect(container.querySelector('code')?.textContent).toContain('<a href=')
  })

  it('is accessible (vitest-axe)', async () => {
    const { container } = render(<EmbedBadgeBox scanId="abc123" score={87} slug="acme--foo" />)
    const results = await axe(container)
    expect(results.violations).toHaveLength(0)
  })
})
