import DotStrip from '@ui/components/atoms/DotStrip'
import Sparkline from '@ui/components/atoms/Sparkline'
import type { CSSProperties } from 'react'

import type { CatalogItemSummary, CatalogSort } from '@/lib/api/items'
import { resolveActivity } from '@/lib/catalog-activity'
import CatalogPagination from './CatalogPagination'
import { bandFromTier, bandOf, kindTag, relativeAge } from './constants'

interface Props {
  items: CatalogItemSummary[]
  page: number
  pageSize: number
  totalCount: number
  totalPages: number
  sort: CatalogSort
  loading: boolean
  emptyVariant?: 'empty-catalog' | 'no-match'
  onSortChange: (sort: CatalogSort) => void
  onPageChange: (page: number) => void
  onItemClick: (item: CatalogItemSummary) => void
}

/**
 * A sortable column header. Each column owns up to two sort STATES — the natural
 * first-click direction and its toggle — each with its own caret glyph + a11y
 * hint, so the caret always reads the live direction (▼ desc value / ▲ asc value)
 * regardless of which direction is "first" for that column. The caret is hidden
 * until hover unless the column is the active sort.
 */
interface SortStateDef {
  key: CatalogSort
  caret: '▲' | '▼'
  hint: string
}
interface SortColumn {
  label: string
  states: [SortStateDef, SortStateDef]
}

function SortHeader({
  column,
  sort,
  onSortChange,
}: {
  column: SortColumn
  sort: CatalogSort
  onSortChange: (sort: CatalogSort) => void
}) {
  const { label, states } = column
  const activeIdx = states.findIndex((s) => s.key === sort)
  const active = activeIdx !== -1
  // Toggle to the other state when active; otherwise start at the first state.
  const next = active ? states[(activeIdx + 1) % states.length].key : states[0].key
  const shown = active ? states[activeIdx] : states[0]
  const ariaLabel = active
    ? `Sorted by ${label.toLowerCase()}, ${shown.hint}`
    : `Sort by ${label.toLowerCase()}`
  return (
    <button
      type="button"
      className={`sort-h${active ? ' active' : ''}`}
      aria-pressed={active}
      aria-label={ariaLabel}
      onClick={() => onSortChange(next)}
    >
      <span>{label}</span>
      <span className="sort-caret" aria-hidden="true">
        {shown.caret}
      </span>
    </button>
  )
}

// ▼ = descending value (most/highest/newest first), ▲ = ascending value.
const TREND_COL: SortColumn = {
  label: 'Trend',
  states: [
    { key: 'most_installed', caret: '▼', hint: 'most installed first' },
    { key: 'least_installed', caret: '▲', hint: 'least installed first' },
  ],
}
const CAPABILITY_COL: SortColumn = {
  label: 'Capability',
  states: [
    { key: 'name_asc', caret: '▲', hint: 'A to Z' },
    { key: 'name_desc', caret: '▼', hint: 'Z to A' },
  ],
}
const SCORE_COL: SortColumn = {
  label: 'Score',
  states: [
    { key: 'highest_score', caret: '▼', hint: 'highest first' },
    { key: 'lowest_score', caret: '▲', hint: 'lowest first' },
  ],
}
const UPDATED_COL: SortColumn = {
  label: 'Updated',
  states: [
    { key: 'recent', caret: '▼', hint: 'newest first' },
    { key: 'oldest', caret: '▲', hint: 'oldest first' },
  ],
}
const ACTIVITY_COL: SortColumn = {
  label: 'Activity',
  states: [
    { key: 'most_active', caret: '▼', hint: 'most active first' },
    { key: 'least_active', caret: '▲', hint: 'least active first' },
  ],
}
const DESCRIPTION_COL: SortColumn = {
  label: 'Description',
  states: [
    { key: 'description_asc', caret: '▲', hint: 'A to Z' },
    { key: 'description_desc', caret: '▼', hint: 'Z to A' },
  ],
}

export default function CatalogResultsList({
  items,
  page,
  pageSize,
  totalCount,
  totalPages,
  sort,
  loading,
  emptyVariant,
  onSortChange,
  onPageChange,
  onItemClick,
}: Props) {
  return (
    <div className="cat-results" aria-busy={loading}>
      <div className="col-head">
        <SortHeader column={TREND_COL} sort={sort} onSortChange={onSortChange} />
        <SortHeader column={CAPABILITY_COL} sort={sort} onSortChange={onSortChange} />
        <SortHeader column={SCORE_COL} sort={sort} onSortChange={onSortChange} />
        <SortHeader column={UPDATED_COL} sort={sort} onSortChange={onSortChange} />
        <SortHeader column={ACTIVITY_COL} sort={sort} onSortChange={onSortChange} />
        <SortHeader column={DESCRIPTION_COL} sort={sort} onSortChange={onSortChange} />
        <div />
      </div>

      {items.length === 0 ? (
        <div className="cat-results-empty" role="status">
          {emptyVariant === 'empty-catalog' ? (
            <>
              <h2>No items indexed yet</h2>
              <p>
                The first ingestion arrives soon. <a href="/scan">Scan one yourself →</a>
              </p>
            </>
          ) : (
            <>
              <h2>No items match these filters</h2>
              <p>Loosen a filter or clear them all to see the full catalog.</p>
            </>
          )}
        </div>
      ) : (
        items.map((item, idx) => {
          const score = item.latest_scan_score ?? 0
          const band = bandFromTier(item.latest_scan_tier, item.latest_scan_score)
          const stripeBand = band ?? bandOf(item.latest_scan_score)
          const rank = ((page - 1) * pageSize + idx + 1).toString().padStart(2, '0')
          const featured = sort === 'most_installed' && page === 1 && idx === 0
          const registries = item.registries.length ? item.registries.join(' · ') : '—'
          const description = item.description?.trim() ? item.description : '—'
          const activity = resolveActivity(item.install_sparkline, item.popularity_score, item.slug)
          return (
            <a
              key={item.id}
              href={`/items/${item.slug}`}
              className={`cat-row stripe-l ${stripeBand}${featured ? ' featured' : ''}`}
              style={{ '--cat-row-i': idx } as CSSProperties}
              onClick={() => onItemClick(item)}
            >
              <div className="rank">{rank}</div>
              <div className="nm">
                <div className="name">{item.display_name}</div>
                <div className="nm-sub">
                  <span className="tag-mini">{kindTag(item.kind)}</span>
                  {item.source_kind === 'upload' && (
                    <span className="tag-mini up" title="Scanned from a directly-uploaded artifact">
                      UPLOAD
                    </span>
                  )}
                  <span className="author">
                    {item.source_kind === 'upload' ? 'uploaded artifact' : item.github_org}
                  </span>
                </div>
              </div>
              <div className="scr">
                <span className="scr-num">
                  <span className="n">{item.latest_scan_score ?? '—'}</span>
                  <span className="denom">/100</span>
                </span>
                <DotStrip value={score} tier={tierName(stripeBand)} />
              </div>
              <div className="meta">
                <span>
                  <span className="star">★ {item.popularity_score}</span> ·{' '}
                  {relativeAge(item.latest_scan_at ?? item.updated_at)}
                </span>
                <span>{registries}</span>
              </div>
              <div className="activity">
                <Sparkline
                  values={activity.values}
                  placeholder={activity.placeholder}
                  width={84}
                  height={24}
                  ariaLabel={
                    activity.placeholder ? 'Install activity: none reported yet' : undefined
                  }
                />
              </div>
              <div className="desc">{description}</div>
              <span className="install-hex">Install</span>
            </a>
          )
        })
      )}
      <CatalogPagination
        page={page}
        pageSize={pageSize}
        totalPages={totalPages}
        totalCount={totalCount}
        itemCount={items.length}
        onPageChange={onPageChange}
      />
    </div>
  )
}

function tierName(band: 'g' | 'y' | 'o' | 'r'): 'green' | 'yellow' | 'orange' | 'red' {
  return { g: 'green', y: 'yellow', o: 'orange', r: 'red' }[band] as
    | 'green'
    | 'yellow'
    | 'orange'
    | 'red'
}
