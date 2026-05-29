import { forwardRef } from 'react'

interface Props {
  query: string
  totalIndexed: number
  registriesCount: number
  onQueryChange: (q: string) => void
  onSubmit: () => void
}

/**
 * Catalog search toolbar — magnifier + mono input + ⌘K hint, plus two live
 * pill-stats (indexed total + registries count) wired to /stats. The parent
 * island owns `query` (controlled) and the ⌘K shortcut focuses this input via
 * the forwarded ref.
 */
const CatalogToolbar = forwardRef<HTMLInputElement, Props>(function CatalogToolbar(
  { query, totalIndexed, registriesCount, onQueryChange, onSubmit },
  ref
) {
  return (
    <section className="cat-toolbar">
      <div className="container">
        <div className="inner">
          <div className="search-wrap">
            <span className="icn" aria-hidden="true">
              <svg
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.8"
                strokeLinecap="round"
                strokeLinejoin="round"
                aria-hidden="true"
              >
                <circle cx="11" cy="11" r="7" />
                <path d="m20 20-3.5-3.5" />
              </svg>
            </span>
            <input
              ref={ref}
              type="text"
              name="q"
              value={query}
              placeholder={`Search ${totalIndexed.toLocaleString()} skills, MCPs and plugins…`}
              autoComplete="off"
              aria-label="Search the catalog"
              onChange={(e) => onQueryChange(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  e.preventDefault()
                  onSubmit()
                }
              }}
            />
            <span className="kbd" aria-hidden="true">
              ⌘&nbsp;K
            </span>
          </div>
          <span className="pill-stat">
            <span className="live" aria-hidden="true" />
            <b>{totalIndexed.toLocaleString()}</b>&nbsp;indexed
          </span>
          <span className="pill-stat">
            <b>{registriesCount.toLocaleString()}</b>&nbsp;registries
          </span>
        </div>
      </div>
    </section>
  )
})

export default CatalogToolbar
