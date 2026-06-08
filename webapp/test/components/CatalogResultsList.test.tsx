import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import CatalogResultsList from '@/components/catalog/CatalogResultsList'
import type { CatalogItemSummary, CatalogSort } from '@/lib/api/items'

function summary(over: Partial<CatalogItemSummary> = {}): CatalogItemSummary {
  return {
    id: 'id-1',
    slug: 'acme--kit--skill-pdf',
    kind: 'skill',
    display_name: 'pdf-extract',
    description: 'Extract text and tables from PDF files',
    github_org: 'acme',
    github_repo: 'kit',
    source_kind: 'github',
    popularity_tier: 'indexed',
    popularity_score: 42,
    latest_scan_score: 80,
    latest_scan_tier: 'green',
    latest_scan_at: '2026-06-02T00:00:00Z',
    findings_count: 0,
    registries: ['npm'],
    agent_compatibility: ['claude-code'],
    updated_at: '2026-06-02T00:00:00Z',
    ...over,
  }
}

function renderList(
  opts: {
    items?: CatalogItemSummary[]
    sort?: CatalogSort
    onSortChange?: (s: CatalogSort) => void
  } = {}
) {
  const onSortChange = opts.onSortChange ?? vi.fn()
  const { unmount } = render(
    <CatalogResultsList
      items={opts.items ?? [summary()]}
      page={1}
      pageSize={10}
      totalCount={1}
      totalPages={1}
      sort={opts.sort ?? 'most_installed'}
      loading={false}
      onSortChange={onSortChange}
      onPageChange={vi.fn()}
      onItemClick={vi.fn()}
    />
  )
  return { onSortChange, unmount }
}

describe('CatalogResultsList', () => {
  it('renders the merged score cell — big number + 10-dot strip together', () => {
    renderList({ items: [summary({ latest_scan_score: 80 })] })
    // the number
    expect(screen.getByText('80')).toBeTruthy()
    expect(screen.getByText('/100')).toBeTruthy()
    // the DotStrip, stacked in the same cell
    const strip = screen.getByRole('img', { name: /score 80 of 100/i })
    expect(strip).toBeTruthy()
    expect(strip.closest('.scr')).not.toBeNull()
  })

  it('renders the dedicated description column (and "—" when absent)', () => {
    const { unmount } = render(
      <CatalogResultsList
        items={[summary({ description: 'A handy little skill' })]}
        page={1}
        pageSize={10}
        totalCount={1}
        totalPages={1}
        sort="most_installed"
        loading={false}
        onSortChange={vi.fn()}
        onPageChange={vi.fn()}
        onItemClick={vi.fn()}
      />
    )
    const desc = screen.getByText('A handy little skill')
    expect(desc.classList.contains('desc')).toBe(true)
    unmount()

    renderList({ items: [summary({ description: null })] })
    expect(screen.getByText('—').classList.contains('desc')).toBe(true)
  })

  it('Trend header toggles most_installed ⇄ least_installed', () => {
    const a = renderList({ sort: 'recent' })
    fireEvent.click(screen.getByRole('button', { name: /trend/i }))
    expect(a.onSortChange).toHaveBeenCalledWith('most_installed')
    a.unmount()

    const b = renderList({ sort: 'most_installed' })
    fireEvent.click(screen.getByRole('button', { name: /trend/i }))
    expect(b.onSortChange).toHaveBeenCalledWith('least_installed')
  })

  it('Capability header sorts by name A→Z then Z→A', () => {
    const a = renderList({ sort: 'most_installed' })
    fireEvent.click(screen.getByRole('button', { name: /capability/i }))
    expect(a.onSortChange).toHaveBeenCalledWith('name_asc')
    a.unmount()

    const b = renderList({ sort: 'name_asc' })
    fireEvent.click(screen.getByRole('button', { name: /capability/i }))
    expect(b.onSortChange).toHaveBeenCalledWith('name_desc')
  })

  it('Updated header toggles recent ⇄ oldest', () => {
    const a = renderList({ sort: 'most_installed' })
    fireEvent.click(screen.getByRole('button', { name: /updated/i }))
    expect(a.onSortChange).toHaveBeenCalledWith('recent')
    a.unmount()

    const b = renderList({ sort: 'recent' })
    fireEvent.click(screen.getByRole('button', { name: /updated/i }))
    expect(b.onSortChange).toHaveBeenCalledWith('oldest')
  })

  it('Activity header toggles most_active ⇄ least_active', () => {
    const a = renderList({ sort: 'most_installed' })
    fireEvent.click(screen.getByRole('button', { name: /activity/i }))
    expect(a.onSortChange).toHaveBeenCalledWith('most_active')
    a.unmount()

    const b = renderList({ sort: 'most_active' })
    fireEvent.click(screen.getByRole('button', { name: /activity/i }))
    expect(b.onSortChange).toHaveBeenCalledWith('least_active')
  })

  it('Description header sorts A→Z then Z→A', () => {
    const a = renderList({ sort: 'most_installed' })
    fireEvent.click(screen.getByRole('button', { name: /description/i }))
    expect(a.onSortChange).toHaveBeenCalledWith('description_asc')
    a.unmount()

    const b = renderList({ sort: 'description_asc' })
    fireEvent.click(screen.getByRole('button', { name: /description/i }))
    expect(b.onSortChange).toHaveBeenCalledWith('description_desc')
  })

  it('renders the Activity sparkline (real data vs popularity-seeded placeholder)', () => {
    const real = renderList({
      items: [summary({ install_sparkline: [0, 0, 2, 0, 1, 0, 0, 3, 0, 0, 1, 0, 4] })],
    })
    // real installs → honest count in the label
    expect(screen.getByRole('img', { name: /11 in the last quarter/i })).toBeTruthy()
    real.unmount()

    // all-zero (or absent) → placeholder, labelled as none-reported (never a fake count)
    renderList({ items: [summary({ install_sparkline: [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0] })] })
    expect(screen.getByRole('img', { name: /none reported yet/i })).toBeTruthy()
  })

  it('Score header toggles highest ⇄ lowest', () => {
    // not yet sorting by score → first click goes to highest
    const a = renderList({ sort: 'most_installed' })
    fireEvent.click(screen.getByRole('button', { name: /score/i }))
    expect(a.onSortChange).toHaveBeenCalledWith('highest_score')
    a.unmount()

    // already highest → click toggles to lowest
    const b = renderList({ sort: 'highest_score' })
    fireEvent.click(screen.getByRole('button', { name: /score/i }))
    expect(b.onSortChange).toHaveBeenCalledWith('lowest_score')
    b.unmount()

    // already lowest → click toggles back to highest
    const c = renderList({ sort: 'lowest_score' })
    fireEvent.click(screen.getByRole('button', { name: /score/i }))
    expect(c.onSortChange).toHaveBeenCalledWith('highest_score')
  })

  it('marks the active sort header as pressed', () => {
    renderList({ sort: 'highest_score' })
    const score = screen.getByRole('button', { name: /score/i })
    expect(score.getAttribute('aria-pressed')).toBe('true')
    const updated = screen.getByRole('button', { name: /updated/i })
    expect(updated.getAttribute('aria-pressed')).toBe('false')
  })

  it('no longer renders the footer Sort dropdown', () => {
    renderList()
    expect(screen.queryByRole('button', { name: /sort catalog/i })).toBeNull()
    expect(screen.queryByText('Sort by')).toBeNull()
  })

  it('stamps the per-row entrance-stagger index', () => {
    renderList({ items: [summary({ id: 'a' }), summary({ id: 'b' })] })
    const rows = document.querySelectorAll('.cat-row')
    expect(rows[0].getAttribute('style')).toContain('--cat-row-i: 0')
    expect(rows[1].getAttribute('style')).toContain('--cat-row-i: 1')
  })

  it('is accessible (vitest-axe)', async () => {
    const { container } = render(
      <CatalogResultsList
        items={[summary()]}
        page={1}
        pageSize={10}
        totalCount={1}
        totalPages={1}
        sort="most_installed"
        loading={false}
        onSortChange={vi.fn()}
        onPageChange={vi.fn()}
        onItemClick={vi.fn()}
      />
    )
    const results = await axe(container)
    expect(results.violations).toHaveLength(0)
  })
})
