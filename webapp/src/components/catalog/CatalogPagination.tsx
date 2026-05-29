interface Props {
  page: number
  totalPages: number
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

export default function CatalogPagination({ page, totalPages, onPageChange }: Props) {
  if (totalPages <= 1) return null
  const items = pageList(page, totalPages)

  return (
    <nav className="cat-pagination" aria-label="Catalog pagination">
      <div className="pg-ct">
        PAGE&nbsp;&nbsp;<b>{page.toLocaleString()}</b>&nbsp;OF&nbsp;{totalPages.toLocaleString()}
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
      <div className="pg-ct">
        JUMP&nbsp;&nbsp;<b>⌘&nbsp;G</b>
      </div>
    </nav>
  )
}
