interface Props {
  page: number
  pageSize: number
  totalPages: number
  totalCount: number
  itemCount: number
  onPageChange: (page: number) => void
}

/** Build the page-button list: first, neighbors of current, last — with gaps. */
function pageList(current: number, total: number): (number | 'gap')[] {
  if (total <= 7) return Array.from({ length: total }, (_, i) => i + 1)
  const delta = 2
  const lo = Math.max(2, current - delta)
  const hi = Math.min(total - 1, current + delta)
  const out: (number | 'gap')[] = [1]
  if (lo > 2) out.push('gap')
  for (let i = lo; i <= hi; i++) out.push(i)
  if (hi < total - 1) out.push('gap')
  out.push(total)
  return out
}

/**
 * Catalog footer: the result-range count (left) and the numbered pager (center).
 * Sorting moved entirely to the clickable column headers, so the old sort picker
 * is gone from here.
 */
export default function CatalogPagination({
  page,
  pageSize,
  totalPages,
  totalCount,
  itemCount,
  onPageChange,
}: Props) {
  const items = pageList(page, Math.max(1, totalPages))
  const start = totalCount === 0 ? 0 : (page - 1) * pageSize + 1
  const end = totalCount === 0 ? 0 : start + itemCount - 1

  return (
    <nav className="cat-pagination" aria-label="Catalog pagination">
      <div className="pg-ct">
        SHOWING&nbsp;&nbsp;
        <b>
          {start}–{end}
        </b>
        &nbsp;OF&nbsp;<b>{totalCount.toLocaleString()}</b>
      </div>
      <div className="pg-nav">
        <button
          type="button"
          className="pg-btn"
          aria-label="Previous page"
          disabled={page <= 1}
          onClick={() => onPageChange(page - 1)}
        >
          ‹
        </button>
        {items.map((it, i) =>
          it === 'gap' ? (
            // biome-ignore lint/suspicious/noArrayIndexKey: static gap marker
            <span key={`gap-${i}`} className="pg-btn gap" aria-hidden="true">
              …
            </span>
          ) : (
            <button
              type="button"
              key={it}
              className={`pg-btn${it === page ? ' active' : ''}`}
              aria-label={`Page ${it}`}
              aria-current={it === page ? 'page' : undefined}
              onClick={() => onPageChange(it)}
            >
              {it}
            </button>
          )
        )}
        <button
          type="button"
          className="pg-btn"
          aria-label="Next page"
          disabled={page >= totalPages}
          onClick={() => onPageChange(page + 1)}
        >
          ›
        </button>
      </div>
    </nav>
  )
}
