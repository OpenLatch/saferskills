import BandPill from '@ui/components/atoms/BandPill'
import DotStrip from '@ui/components/atoms/DotStrip'
import ScoreNumber from '@ui/components/atoms/ScoreNumber'

import { track } from '@/lib/analytics'
import type { CatalogItemSummary, ScanTier } from '@/lib/api/items'

interface Props {
  items: CatalogItemSummary[]
  nextCursor: string | null
  prevCursor?: string | null
  totalCount: number
  emptyVariant?: 'empty-catalog' | 'no-match'
}

function _tier(score: number | null | undefined): 'green' | 'yellow' | 'orange' | 'red' {
  if (score == null) return 'red'
  if (score >= 80) return 'green'
  if (score >= 60) return 'yellow'
  if (score >= 40) return 'orange'
  return 'red'
}

export default function CatalogResultsList({ items, nextCursor, totalCount, emptyVariant }: Props) {
  if (items.length === 0) {
    return (
      <div className="cat-results cat-results-empty" role="status">
        {emptyVariant === 'empty-catalog' ? (
          <>
            <h2>No items indexed yet</h2>
            <p>
              The first ingestion arrives next week. <a href="/scan">Scan one yourself →</a>
            </p>
          </>
        ) : (
          <>
            <h2>No items match these filters</h2>
            <p>
              <a href="/catalog">Clear all filters</a> to see the full catalog.
            </p>
          </>
        )}
      </div>
    )
  }

  function handleRowClick(item: CatalogItemSummary) {
    track('catalog_item_clicked', {
      tier: (item.latest_scan_tier ?? 'unscoped') as
        | 'green'
        | 'yellow'
        | 'orange'
        | 'red'
        | 'unscoped',
      kind: item.kind,
    })
  }

  return (
    <section className="cat-results" aria-label="Catalog items">
      <header className="col-head">
        <span>#</span>
        <span>Name · Author · Description</span>
        <span>Score</span>
        <span>Dots</span>
        <span>Band</span>
        <span>Meta</span>
        <span>Install</span>
      </header>
      <ul className="cat-results-rows">
        {items.map((item, idx) => {
          const score = item.latest_scan_score ?? 0
          const tier = (item.latest_scan_tier as ScanTier | undefined) ?? 'unscoped'
          return (
            <li key={item.id} className={`cat-row${idx === 0 ? ' featured' : ''}`}>
              <a
                href={`/items/${item.slug}`}
                className="cat-row-link"
                onClick={() => handleRowClick(item)}
              >
                <span className="cat-row-rank">{(idx + 1).toString().padStart(3, '0')}</span>
                <span className="cat-row-name">
                  <strong>{item.display_name}</strong>
                  <span className="cat-row-author">{item.github_org}</span>
                  {item.description ? (
                    <span className="cat-row-desc">{item.description}</span>
                  ) : null}
                </span>
                <span className="cat-row-score">
                  <ScoreNumber value={score} size="md" />
                  <span className="cat-row-slash">/100</span>
                </span>
                <span className="cat-row-dots">
                  <DotStrip value={score} tier={_tier(score)} />
                </span>
                <span className="cat-row-band">
                  {tier !== 'unscoped' ? (
                    <BandPill tier={tier as 'green' | 'yellow' | 'orange' | 'red'} />
                  ) : (
                    <span className="band-pill unscoped">UNSCOPED</span>
                  )}
                </span>
                <span className="cat-row-meta">
                  {item.popularity_score > 0 ? <span>★ {item.popularity_score}</span> : null}
                  <span>
                    {item.registries.length} reg{item.registries.length === 1 ? '' : 's'}
                  </span>
                  <span>
                    {item.findings_count} finding{item.findings_count === 1 ? '' : 's'}
                  </span>
                </span>
                <span className="cat-row-install btn btn-hex btn-primary">
                  <span className="btn-hex-cap" aria-hidden="true" />
                  <span className="btn-label">INSTALL</span>
                </span>
              </a>
            </li>
          )
        })}
      </ul>
      <nav className="cat-pagination" aria-label="Catalog pagination">
        <span>
          {items.length} of {totalCount.toLocaleString()}
        </span>
        {nextCursor ? (
          <a href={`/catalog?cursor=${encodeURIComponent(nextCursor)}`}>Next →</a>
        ) : null}
      </nav>
    </section>
  )
}
