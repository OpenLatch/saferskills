import type { ReactNode } from 'react'
import { useCallback, useEffect, useRef, useState } from 'react'

/**
 * Render a Pagefind excerpt (page text with `<mark>` highlights) as React —
 * parse with DOMParser and emit ONLY text nodes + `<mark>` spans. No raw-HTML
 * injection (no dangerouslySetInnerHTML), and the browser decodes entities.
 */
function renderExcerpt(html: string): ReactNode[] {
  const body = new DOMParser().parseFromString(html, 'text/html').body
  return Array.from(body.childNodes).map((node, i) => {
    if (node.nodeName === 'MARK') {
      // biome-ignore lint/suspicious/noArrayIndexKey: static parsed segments, stable order
      return <mark key={i}>{node.textContent}</mark>
    }
    return node.textContent
  })
}

/**
 * Docs full-text search (I-06 native rebuild) — a DS-styled trigger + ⌘K modal
 * over the Pagefind index built post-`astro build` (`scripts/build-pagefind.cjs`
 * → `/pagefind/pagefind.js`). The index only exists in a real build, so in
 * `astro dev` the dynamic import fails and the box degrades to a disabled hint
 * — never throws. CSS in `webapp/src/styles/page-docs.css`.
 */
interface PagefindResult {
  url: string
  meta: { title?: string }
  excerpt: string
}
interface PagefindApi {
  init?: () => Promise<void>
  search: (q: string) => Promise<{ results: { data: () => Promise<PagefindResult> }[] }>
}

let pagefindPromise: Promise<PagefindApi | null> | null = null
function loadPagefind(): Promise<PagefindApi | null> {
  if (!pagefindPromise) {
    // `/pagefind/pagefind.js` is emitted at build, not resolvable by Vite —
    // @vite-ignore keeps it a true runtime import. Null on failure (dev / no index).
    const url = '/pagefind/pagefind.js'
    pagefindPromise = import(/* @vite-ignore */ url)
      .then(async (mod: PagefindApi) => {
        await mod.init?.()
        return mod
      })
      .catch(() => null)
  }
  return pagefindPromise
}

export default function DocsSearch() {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<PagefindResult[]>([])
  const [available, setAvailable] = useState(true)
  const [loading, setLoading] = useState(false)
  const dialogRef = useRef<HTMLDialogElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  const openModal = useCallback(() => setOpen(true), [])
  const closeModal = useCallback(() => setOpen(false), [])

  // ⌘K / Ctrl-K opens; the dialog's own Escape closes it.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault()
        setOpen((v) => !v)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  // Drive the native <dialog> from `open`; focus the input on show.
  useEffect(() => {
    const dlg = dialogRef.current
    if (!dlg) return
    if (open && !dlg.open) {
      dlg.showModal()
      inputRef.current?.focus()
    } else if (!open && dlg.open) {
      dlg.close()
    }
  }, [open])

  // Query Pagefind (debounced); degrade gracefully when the index is absent.
  useEffect(() => {
    if (!open) return
    const q = query.trim()
    if (!q) {
      setResults([])
      setLoading(false)
      return
    }
    setLoading(true)
    let cancelled = false
    const t = window.setTimeout(async () => {
      const pf = await loadPagefind()
      if (cancelled) return
      if (!pf) {
        setAvailable(false)
        setLoading(false)
        return
      }
      setAvailable(true)
      try {
        const search = await pf.search(q)
        const data = await Promise.all(search.results.slice(0, 8).map((r) => r.data()))
        if (!cancelled) setResults(data)
      } catch {
        if (!cancelled) setResults([])
      } finally {
        if (!cancelled) setLoading(false)
      }
    }, 160)
    return () => {
      cancelled = true
      window.clearTimeout(t)
    }
  }, [query, open])

  return (
    <>
      <button type="button" className="docs-search-trigger" onClick={openModal}>
        <svg
          viewBox="0 0 16 16"
          width="14"
          height="14"
          aria-hidden="true"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.6"
        >
          <circle cx="7" cy="7" r="4.5" />
          <path d="M11 11l3.5 3.5" strokeLinecap="round" />
        </svg>
        <span>Search</span>
        <kbd className="docs-search-kbd">⌘K</kbd>
      </button>

      {/* biome-ignore lint/a11y/useKeyWithClickEvents: backdrop click-to-dismiss only; keyboard users close via the native <dialog> Escape (onClose) */}
      <dialog
        ref={dialogRef}
        className="docs-search-modal"
        aria-label="Search the documentation"
        onClose={closeModal}
        onClick={(e) => {
          if (e.target === dialogRef.current) closeModal()
        }}
      >
        <div className="dsm-inner">
          <div className="dsm-field">
            <svg
              viewBox="0 0 16 16"
              width="16"
              height="16"
              aria-hidden="true"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.6"
            >
              <circle cx="7" cy="7" r="4.5" />
              <path d="M11 11l3.5 3.5" strokeLinecap="round" />
            </svg>
            <input
              ref={inputRef}
              type="search"
              className="dsm-input"
              placeholder="Search the docs…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              aria-label="Search the documentation"
            />
            {loading && <span className="dsm-spinner" aria-hidden="true" />}
            <kbd className="docs-search-kbd">Esc</kbd>
          </div>
          <div className="dsm-results" aria-busy={loading}>
            {!available && (
              <p className="dsm-empty">Full-text search is available in the production build.</p>
            )}
            {available && !query.trim() && (
              <p className="dsm-empty">Type to search the documentation.</p>
            )}
            {available && query.trim() && loading && results.length === 0 && (
              <p className="dsm-empty">Searching…</p>
            )}
            {available && query.trim() && !loading && results.length === 0 && (
              <p className="dsm-empty">No results for “{query.trim()}”.</p>
            )}
            <ul>
              {results.map((r) => (
                <li key={r.url}>
                  <a className="dsm-result" href={r.url}>
                    <strong>{r.meta?.title ?? r.url}</strong>
                    <span className="dsm-excerpt">{renderExcerpt(r.excerpt)}</span>
                  </a>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </dialog>
    </>
  )
}
