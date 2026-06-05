import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import CatalogPagination from '@/components/catalog/CatalogPagination'

function renderPager(over: Partial<Parameters<typeof CatalogPagination>[0]> = {}) {
  const onPageChange = over.onPageChange ?? vi.fn()
  render(
    <CatalogPagination
      page={2}
      pageSize={10}
      totalPages={5}
      totalCount={48}
      itemCount={10}
      onPageChange={onPageChange}
      {...over}
    />
  )
  return { onPageChange }
}

describe('CatalogPagination', () => {
  it('renders the result-range count', () => {
    renderPager()
    // page 2 of size 10 → 11–20 of 48
    expect(screen.getByText('11–20')).toBeTruthy()
    expect(screen.getByText('48')).toBeTruthy()
  })

  it('changes page when a numbered button is clicked', () => {
    const { onPageChange } = renderPager()
    fireEvent.click(screen.getByRole('button', { name: 'Page 3' }))
    expect(onPageChange).toHaveBeenCalledWith(3)
  })

  it('does not render the sort dropdown (sorting moved to column headers)', () => {
    renderPager()
    expect(screen.queryByRole('button', { name: /sort catalog/i })).toBeNull()
    expect(screen.queryByText('Sort by')).toBeNull()
  })

  it('is accessible (vitest-axe)', async () => {
    const { container } = render(
      <CatalogPagination
        page={2}
        pageSize={10}
        totalPages={5}
        totalCount={48}
        itemCount={10}
        onPageChange={vi.fn()}
      />
    )
    const results = await axe(container)
    expect(results.violations).toHaveLength(0)
  })
})
