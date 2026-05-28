import { useEffect, useRef, useState } from 'react'

interface Props {
  totalCount: number
  initialQuery?: string
}

export default function CatalogToolbar({ totalCount, initialQuery = '' }: Props) {
  const [query, setQuery] = useState(initialQuery)
  const inputRef = useRef<HTMLInputElement>(null)

  // ⌘K / Ctrl+K focuses the search bar.
  useEffect(() => {
    function handleShortcut(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault()
        inputRef.current?.focus()
        inputRef.current?.select()
      }
    }
    window.addEventListener('keydown', handleShortcut)
    return () => window.removeEventListener('keydown', handleShortcut)
  }, [])

  return (
    <form className="cat-toolbar" action="/catalog" method="GET">
      <div className="cat-toolbar-search">
        <label className="cat-toolbar-search-label" htmlFor="cat-toolbar-query">
          <span className="cat-toolbar-search-icon" aria-hidden="true">
            ⌕
          </span>
          <input
            id="cat-toolbar-query"
            ref={inputRef}
            type="text"
            name="q"
            placeholder="Search by name, repo, or rule_id"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            autoComplete="off"
            aria-label="Catalog search"
          />
          <kbd className="cat-toolbar-search-kbd">⌘K</kbd>
        </label>
      </div>
      <div className="cat-toolbar-counter">
        <span className="eyebrow eyebrow-rule">{totalCount.toLocaleString()} INDEXED</span>
        <span className="cat-toolbar-counter-pulse" aria-hidden="true" />
        <span className="cat-toolbar-counter-live">LIVE</span>
      </div>
    </form>
  )
}
