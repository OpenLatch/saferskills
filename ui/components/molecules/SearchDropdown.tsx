import { Command } from 'cmdk'
import { useEffect, useId, useRef, useState } from 'react'
import type { RefObject } from 'react'
import SearchDropdownItem, { type SearchHit } from './SearchDropdownItem'

export interface SearchGroup {
  kind: string
  label: string
  hits: SearchHit[]
}

interface Props {
  /** Live query string from the host input. */
  query: string
  /** Ref to the host input — used for focus restoration, ARIA wiring, and outside-click detection. */
  inputRef: RefObject<HTMLInputElement | null>
  /** Async search; must return groups already filtered + sorted. AbortController fires on rapid retype. */
  search: (query: string, signal?: AbortSignal) => Promise<SearchGroup[]>
  /** Activated when the user picks a row (mouse or Enter). */
  onSelect: (hit: SearchHit) => void
  /** Slugs to render as suggestion chips when the input is focused but empty. */
  zeroStateSuggestions?: readonly string[]
  /** Where to send the user when they hit Enter with no row selected. */
  fallbackHref?: (query: string) => string
}

const DEBOUNCE_MS = 300

type LoadState =
  | { phase: 'idle' }
  | { phase: 'loading' }
  | { phase: 'ready'; groups: SearchGroup[] }
  | { phase: 'error' }

/**
 * Inline command-palette dropdown anchored below an input. Generic over the
 * search source — the consumer passes a `search` callback so the molecule
 * has no opinion about how results are fetched (mock JSON at W1, HTTP at
 * W2 once `/api/v1/catalog/search` ships).
 *
 * Owns:
 *   - open/close state driven by focus + query
 *   - debounced fetch with AbortController
 *   - cmdk listbox semantics (ArrowDown/Up, Enter, Escape)
 *   - aria-activedescendant wiring back onto the host input
 *   - zero / loading / ready / no-results / error UI states
 */
export default function SearchDropdown({
  query,
  inputRef,
  search,
  onSelect,
  zeroStateSuggestions = [],
  fallbackHref,
}: Props) {
  const listboxId = useId()
  const [focused, setFocused] = useState(false)
  const [state, setState] = useState<LoadState>({ phase: 'idle' })
  const [activeValue, setActiveValue] = useState<string>('')
  const wrapperRef = useRef<HTMLDivElement>(null)

  const open = focused || query.trim().length > 0

  useEffect(() => {
    const input = inputRef.current
    if (!input) return
    const onFocus = () => setFocused(true)
    const onBlur = (e: FocusEvent) => {
      const next = e.relatedTarget as Node | null
      if (next && wrapperRef.current?.contains(next)) return
      setFocused(false)
    }
    input.addEventListener('focus', onFocus)
    input.addEventListener('blur', onBlur)
    return () => {
      input.removeEventListener('focus', onFocus)
      input.removeEventListener('blur', onBlur)
    }
  }, [inputRef])

  useEffect(() => {
    if (!open) return
    const onPointerDown = (e: PointerEvent) => {
      const target = e.target as Node | null
      if (!target) return
      if (wrapperRef.current?.contains(target)) return
      if (inputRef.current?.contains(target)) return
      setFocused(false)
      inputRef.current?.blur()
    }
    document.addEventListener('pointerdown', onPointerDown)
    return () => document.removeEventListener('pointerdown', onPointerDown)
  }, [open, inputRef])

  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return
      e.preventDefault()
      setFocused(false)
      inputRef.current?.blur()
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [open, inputRef])

  useEffect(() => {
    const input = inputRef.current
    if (!input || !fallbackHref) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 'Enter') return
      const q = query.trim()
      if (!q) return
      if (activeValue) return
      e.preventDefault()
      window.location.assign(fallbackHref(q))
    }
    input.addEventListener('keydown', onKey)
    return () => input.removeEventListener('keydown', onKey)
  }, [query, activeValue, inputRef, fallbackHref])

  useEffect(() => {
    const q = query.trim()
    if (!q) {
      setState({ phase: 'idle' })
      return
    }
    setState({ phase: 'loading' })
    const ctrl = new AbortController()
    const timer = setTimeout(async () => {
      try {
        const groups = await search(q, ctrl.signal)
        if (ctrl.signal.aborted) return
        setState({ phase: 'ready', groups })
      } catch (err) {
        if ((err as { name?: string }).name === 'AbortError') return
        setState({ phase: 'error' })
      }
    }, DEBOUNCE_MS)
    return () => {
      ctrl.abort()
      clearTimeout(timer)
    }
  }, [query, search])

  useEffect(() => {
    const input = inputRef.current
    if (!input) return
    input.setAttribute('role', 'combobox')
    input.setAttribute('aria-autocomplete', 'list')
    input.setAttribute('aria-controls', listboxId)
    input.setAttribute('aria-expanded', open ? 'true' : 'false')
  }, [open, listboxId, inputRef])

  useEffect(() => {
    const input = inputRef.current
    if (!input) return
    if (!open || !activeValue) {
      input.removeAttribute('aria-activedescendant')
      return
    }
    input.setAttribute('aria-activedescendant', toOptionId(listboxId, activeValue))
  }, [activeValue, open, listboxId, inputRef])

  if (!open) return null

  const q = query.trim()
  const groups = state.phase === 'ready' ? state.groups : []
  const hitCount = groups.reduce((sum, g) => sum + g.hits.length, 0)

  function pickSuggestion(slug: string) {
    onSelect({
      kind: 'unknown',
      slug,
      display_name: slug,
      editor: '',
      scan_score: 0,
      severity: 'info',
    })
  }

  return (
    <div ref={wrapperRef} className="search-dropdown" role="presentation">
      <Command
        shouldFilter={false}
        value={activeValue}
        onValueChange={setActiveValue}
        loop
        label="Catalog search"
      >
        <Command.List id={listboxId} role="listbox">
          {!q && zeroStateSuggestions.length > 0 && (
            <div className="search-dropdown-zero">
              <span className="search-dropdown-group-label">Try</span>
              <div className="search-dropdown-chips">
                {zeroStateSuggestions.map((slug) => (
                  <button
                    key={slug}
                    type="button"
                    className="search-dropdown-chip"
                    onClick={() => pickSuggestion(slug)}
                  >
                    {slug}
                  </button>
                ))}
              </div>
            </div>
          )}

          {q && state.phase === 'loading' && (
            <div className="search-dropdown-loading" aria-busy="true">
              <div className="search-dropdown-skeleton" />
              <div className="search-dropdown-skeleton" />
              <div className="search-dropdown-skeleton" />
            </div>
          )}

          {q && state.phase === 'error' && (
            <div className="search-dropdown-error">
              <span>Search failed.</span>
              <button
                type="button"
                className="search-dropdown-retry"
                onClick={() => {
                  setState({ phase: 'loading' })
                  search(q)
                    .then((groups) => setState({ phase: 'ready', groups }))
                    .catch(() => setState({ phase: 'error' }))
                }}
              >
                Retry
              </button>
            </div>
          )}

          {q &&
            state.phase === 'ready' &&
            groups.map((group) => (
              <Command.Group
                key={group.kind}
                heading={group.label}
                className="search-dropdown-group"
              >
                {group.hits.map((hit) => (
                  <SearchDropdownItem
                    key={`${hit.kind}:${hit.slug}`}
                    hit={hit}
                    onSelect={onSelect}
                    id={toOptionId(listboxId, `${hit.kind}:${hit.slug}`)}
                  />
                ))}
              </Command.Group>
            ))}

          {q && state.phase === 'ready' && hitCount === 0 && (
            <div className="search-dropdown-empty">
              <p>
                No results for <span className="q">&ldquo;{q}&rdquo;</span>
              </p>
              {zeroStateSuggestions.length > 0 && (
                <div className="search-dropdown-chips">
                  {zeroStateSuggestions.map((slug) => (
                    <button
                      key={slug}
                      type="button"
                      className="search-dropdown-chip"
                      onClick={() => pickSuggestion(slug)}
                    >
                      {slug}
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}
        </Command.List>
      </Command>
    </div>
  )
}

function toOptionId(listboxId: string, value: string): string {
  return `${listboxId}-opt-${value.replace(/[^a-z0-9_-]+/gi, '-')}`
}
