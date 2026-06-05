import DotStrip from '@ui/components/atoms/DotStrip'
import type { CSSProperties } from 'react'

import type { CatalogItemSummary, CatalogSort } from '@/lib/api/items'
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
 * A sortable column header. Owns a primary (desc) sort key and, optionally, a
 * secondary (asc) key it toggles to. The caret is hidden until hover unless the
 * column is the active sort, where it shows the live direction (▼ desc / ▲ asc).
 */
interface SortColumn {
  label: string
  descKey: CatalogSort
  ascKey?: CatalogSort
  /** Human phrase for the desc direction, e.g. "highest first". */
  descHint: string
  /** Human phrase for the asc direction (only when `ascKey` is set). */
  ascHint?: string
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
  const { label, descKey, ascKey, descHint, ascHint } = column
  const isAsc = ascKey != null && sort === ascKey
  const isDesc = sort === descKey
  const active = isAsc || isDesc
  // Clicking a two-way column toggles desc⇄asc; a one-way column always sorts desc.
  const next: CatalogSort = ascKey != null && isDesc ? ascKey : descKey
  const ariaLabel = active
    ? `Sorted by ${label.toLowerCase()}, ${isAsc ? ascHint : descHint}`
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
        {isAsc ? '▲' : '▼'}
      </span>
    </button>
  )
}

const TREND_COL: SortColumn = {
  label: 'Trend',
  descKey: 'most_installed',
  descHint: 'trending first',
}
const SCORE_COL: SortColumn = {
  label: 'Score',
  descKey: 'highest_score',
  ascKey: 'lowest_score',
  descHint: 'highest first',
  ascHint: 'lowest first',
}
const UPDATED_COL: SortColumn = {
  label: 'Updated',
  descKey: 'recent',
  descHint: 'most recent first',
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
        <div>Capability</div>
        <SortHeader column={SCORE_COL} sort={sort} onSortChange={onSortChange} />
        <SortHeader column={UPDATED_COL} sort={sort} onSortChange={onSortChange} />
        <div>Description</div>
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
