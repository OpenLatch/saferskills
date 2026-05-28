import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { axe } from 'vitest-axe'
import ActionCard from '../../../components/molecules/ActionCard'

describe('ActionCard', () => {
  it('renders index + kicker + title + lede + children', () => {
    render(
      <ActionCard
        index="01"
        kicker="FIND"
        liveLabel="INDEXING"
        title="Search the catalog."
        lede="12,847 indexed."
      >
        <input aria-label="Catalog search" />
      </ActionCard>,
    )
    expect(screen.getByText('01')).toBeInTheDocument()
    expect(screen.getByText('FIND')).toBeInTheDocument()
    expect(screen.getByText('INDEXING')).toBeInTheDocument()
    expect(screen.getByRole('heading', { level: 3 })).toHaveTextContent('Search the catalog.')
    expect(screen.getByLabelText('Catalog search')).toBeInTheDocument()
  })

  it('renders without live label', () => {
    render(
      <ActionCard index="02" kicker="AUDIT" title="Scan." lede="Free.">
        <button type="button">Go</button>
      </ActionCard>,
    )
    expect(screen.queryByText('INDEXING')).not.toBeInTheDocument()
  })

  it('is accessible (vitest-axe)', async () => {
    const { container } = render(
      <ActionCard index="01" kicker="FIND" title="Search the catalog." lede="lede.">
        <input aria-label="X" />
      </ActionCard>,
    )
    const results = await axe(container)
    expect(results.violations).toHaveLength(0)
  })
})
