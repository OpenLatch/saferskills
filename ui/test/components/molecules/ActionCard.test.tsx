import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { axe } from 'vitest-axe'
import ActionCard from '../../../components/molecules/ActionCard'

describe('ActionCard', () => {
  it('renders sequence + kicker + title + lede + children inside the p1-card head/body', () => {
    const { container } = render(
      <ActionCard
        index="01"
        kicker="Find"
        liveLabel="Indexing"
        title="Search the catalog."
        lede="12,847 indexed."
        variant="find"
      >
        <input aria-label="Catalog search" />
      </ActionCard>,
    )
    expect(container.querySelector('.p1-card.find')).not.toBeNull()
    expect(container.querySelector('.p1-head .seq')?.textContent).toBe('01')
    expect(screen.getByText('Find')).toBeInTheDocument()
    expect(screen.getByText('Indexing')).toBeInTheDocument()
    expect(screen.getByRole('heading', { level: 3 })).toHaveTextContent('Search the catalog.')
    expect(screen.getByLabelText('Catalog search')).toBeInTheDocument()
  })

  it('omits the .pulse strip when no liveLabel is provided', () => {
    const { container } = render(
      <ActionCard index="02" kicker="Audit" title="Scan." lede="Free." variant="audit">
        <button type="button">Go</button>
      </ActionCard>,
    )
    expect(container.querySelector('.p1-head .pulse')).toBeNull()
  })

  it('renders the foot with a CTA link and meta strip when foot is provided', () => {
    render(
      <ActionCard
        index="01"
        kicker="Find"
        title="Search."
        lede="lede."
        foot={{
          cta: { label: 'Browse catalog →', href: '/catalog' },
          meta: <><b>12,847</b> indexed</>,
        }}
      >
        <input aria-label="X" />
      </ActionCard>,
    )
    const link = screen.getByRole('link', { name: /Browse catalog/ })
    expect(link).toHaveAttribute('href', '/catalog')
    expect(screen.getByText('12,847')).toBeInTheDocument()
    // The trailing arrow is split into its own aria-hidden span so it can be
    // animated (slide) independently of the label on hover.
    const arrow = link.querySelector('.p1-cta-arrow')
    expect(arrow?.textContent).toBe('→')
    expect(arrow).toHaveAttribute('aria-hidden', 'true')
    // Accessible name excludes the decorative arrow.
    expect(link).toHaveAccessibleName('Browse catalog')
  })

  it('is accessible (vitest-axe)', async () => {
    const { container } = render(
      <ActionCard index="01" kicker="Find" title="Search the catalog." lede="lede.">
        <input aria-label="X" />
      </ActionCard>,
    )
    const results = await axe(container)
    expect(results.violations).toHaveLength(0)
  })
})
