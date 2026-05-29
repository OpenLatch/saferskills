import BandPill from '@ui/components/atoms/BandPill'
import DotStrip from '@ui/components/atoms/DotStrip'

import type { CatalogItemSummary, CatalogSort } from '@/lib/api/items'
import CatalogPagination from './CatalogPagination'
import { bandFromTier, bandOf, kindTag, relativeAge, SORT_OPTIONS, sortLabel } from './constants'

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
  const start = totalCount === 0 ? 0 : (page - 1) * pageSize + 1
  const end = totalCount === 0 ? 0 : start + items.length - 1

  return (
    <div className="cat-results" aria-busy={loading}>
      <div className="ribbon">
        <span>
          Showing{' '}
          <b>
            {start}–{end}
          </b>{' '}
          of <b>{totalCount.toLocaleString()}</b>
        </span>
        <span className="sort">
          <span>Sort by</span>
          <span className="picker">
            {sortLabel(sort)}
            <svg
              width="9"
              height="6"
              viewBox="0 0 9 6"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.4"
              aria-hidden="true"
            >
              <path d="M1 1l3.5 3L8 1" />
            </svg>
            <select
              value={sort}
              aria-label="Sort catalog"
              onChange={(e) => onSortChange(e.target.value as CatalogSort)}
            >
              {SORT_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
          </span>
        </span>
      </div>

      <div className="col-head">
        <div>#</div>
        <div>Name · author · description</div>
        <div>Score</div>
        <div>Dots</div>
        <div>Band</div>
        <div>Stars · age · registries</div>
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
          return (
            <a
              key={item.id}
              href={`/items/${item.slug}`}
              className={`cat-row stripe-l ${stripeBand}${featured ? ' featured' : ''}`}
              onClick={() => onItemClick(item)}
            >
              <div className="rank">{rank}</div>
              <div className="nm">
                <div className="name">{item.display_name}</div>
                <div className="desc">
                  <span className="tag-mini">{kindTag(item.kind)}</span>
                  <span>
                    {item.github_org}
                    {item.description ? ` · ${item.description}` : ''}
                  </span>
                </div>
              </div>
              <div className="scr">
                <span className="n">{item.latest_scan_score ?? '—'}</span>
                <span className="denom">/100</span>
              </div>
              <div className="dots">
                <DotStrip value={score} tier={tierName(stripeBand)} />
              </div>
              <div>
                {band ? (
                  <BandPill tier={tierName(band)} />
                ) : (
                  <span className="band-pill">Unscoped</span>
                )}
              </div>
              <div className="meta">
                <span>
                  <span className="star">★ {item.popularity_score}</span> ·{' '}
                  {relativeAge(item.latest_scan_at ?? item.updated_at)}
                </span>
                <span>{registries}</span>
              </div>
              <span className="install-hex">Install</span>
            </a>
          )
        })
      )}
      <CatalogPagination page={page} totalPages={totalPages} onPageChange={onPageChange} />
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
