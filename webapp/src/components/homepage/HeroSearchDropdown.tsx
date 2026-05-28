import { Command } from 'cmdk'
import type { RefObject } from 'react'
import { useEffect, useId, useRef, useState } from 'react'
import { type CatalogHit, groupByKind, KIND_LABELS, searchCatalog } from '@/lib/catalog-search'
import HeroSearchItem from './HeroSearchItem'

interface Props {
  query: string
  inputRef: RefObject<HTMLInputElement | null>
  onSelect: (slug: string) => void
}

const DEBOUNCE_MS = 300

const ZERO_STATE_CHIPS = ['claude-pdf', 'github-mcp', 'slack-bot', 'ripgrep-skill', 'obsidian-mcp']

type LoadState =
  | { phase: 'idle' }
  | { phase: 'loading' }
  | { phase: 'ready'; hits: CatalogHit[] }
  | { phase: 'error' }

/**
 * Inline dropdown positioned below the hero Find input. Owns:
 *   - open/close state driven by focus + query
 *   - debounced fetch with AbortController
 *   - cmdk listbox semantics (ArrowDown/Up, Enter, Escape)
 *   - aria-activedescendant wiring back onto the parent input
 */
export default function HeroSearchDropdown({ query, inputRef, onSelect }: Props) {
  const listboxId = useId()
  const [focused, setFocused] = useState(false)
  const [state, setState] = useState<LoadState>({ phase: 'idle' })
  const [activeValue, setActiveValue] = useState<string>('')
  const wrapperRef = useRef<HTMLDivElement>(null)

  // open = input focused OR query non-empty (so a click into the chip
  // suggestions doesn't close the panel before the click registers)
  const open = focused || query.trim().length > 0

  useEffect(() => {
    const input = inputRef.current
    if (!input) return
    const onFocus = () => setFocused(true)
    const onBlur = (e: FocusEvent) => {
      // keep open if focus moved into the dropdown (a chip / row)
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

  // Outside-click closes the panel
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

  // Escape closes & restores focus
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return
      e.preventDefault()
      setFocused(false)
      inputRef.current?.focus()
      inputRef.current?.blur()
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [open, inputRef])

  // Enter-without-active-row navigates to /catalog?q=...
  useEffect(() => {
    const input = inputRef.current
    if (!input) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 'Enter') return
      const q = query.trim()
      if (!q) return
      if (activeValue) return // cmdk handles the selected row
      e.preventDefault()
      window.location.assign(`/catalog?q=${encodeURIComponent(q)}`)
    }
    input.addEventListener('keydown', onKey)
    return () => input.removeEventListener('keydown', onKey)
  }, [query, activeValue, inputRef])

  // Debounced fetch
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
        const hits = await searchCatalog(q, ctrl.signal)
        if (ctrl.signal.aborted) return
        setState({ phase: 'ready', hits })
      } catch (err) {
        if ((err as { name?: string }).name === 'AbortError') return
        setState({ phase: 'error' })
      }
    }, DEBOUNCE_MS)
    return () => {
      ctrl.abort()
      clearTimeout(timer)
    }
  }, [query])

  // Wire aria-activedescendant on the input
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
    input.setAttribute('aria-activedescendant', activeOptionId(listboxId, activeValue))
  }, [activeValue, open, listboxId, inputRef])

  if (!open) return null

  const hits = state.phase === 'ready' ? state.hits : []
  const groups = groupByKind(hits)
  const q = query.trim()

  return (
    <div ref={wrapperRef} className="p1-dropdown" role="presentation">
      <Command
        shouldFilter={false}
        value={activeValue}
        onValueChange={setActiveValue}
        loop
        label="Catalog search"
      >
        <Command.List id={listboxId} role="listbox">
          {/* Zero-state: focused, empty query */}
          {!q && (
            <div className="p1-dropdown-zero">
              <span className="p1-dropdown-group-label">Try</span>
              <div className="p1-dropdown-chips">
                {ZERO_STATE_CHIPS.map((slug) => (
                  <button
                    key={slug}
                    type="button"
                    className="p1-dropdown-chip"
                    onClick={() => onSelect(slug)}
                  >
                    {slug}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Loading skeletons */}
          {q && state.phase === 'loading' && (
            <div className="p1-dropdown-loading" aria-busy="true">
              <div className="p1-dropdown-skeleton" />
              <div className="p1-dropdown-skeleton" />
              <div className="p1-dropdown-skeleton" />
            </div>
          )}

          {/* Error */}
          {q && state.phase === 'error' && (
            <div className="p1-dropdown-error">
              <span>Search failed.</span>
              <button
                type="button"
                className="p1-dropdown-retry"
                onClick={() => {
                  setState({ phase: 'idle' })
                  // trigger re-fetch by nudging state — the effect keys on query
                  setState({ phase: 'loading' })
                  searchCatalog(q)
                    .then((hits) => setState({ phase: 'ready', hits }))
                    .catch(() => setState({ phase: 'error' }))
                }}
              >
                Retry
              </button>
            </div>
          )}

          {/* Results */}
          {q &&
            state.phase === 'ready' &&
            groups.map((group) => (
              <Command.Group
                key={group.kind}
                heading={KIND_LABELS[group.kind]}
                className="p1-dropdown-group"
              >
                {group.hits.map((hit) => (
                  <HeroSearchItem
                    key={`${hit.kind}:${hit.slug}`}
                    hit={hit}
                    onSelect={onSelect}
                    id={activeOptionId(listboxId, `${hit.kind}:${hit.slug}`)}
                  />
                ))}
              </Command.Group>
            ))}

          {/* No results */}
          {q && state.phase === 'ready' && hits.length === 0 && (
            <div className="p1-dropdown-empty">
              <p>
                No skills found for <span className="q">&ldquo;{q}&rdquo;</span>
              </p>
              <div className="p1-dropdown-chips">
                {ZERO_STATE_CHIPS.map((slug) => (
                  <button
                    key={slug}
                    type="button"
                    className="p1-dropdown-chip"
                    onClick={() => onSelect(slug)}
                  >
                    {slug}
                  </button>
                ))}
              </div>
            </div>
          )}
        </Command.List>
      </Command>
    </div>
  )
}

function activeOptionId(listboxId: string, value: string): string {
  return `${listboxId}-opt-${value.replace(/[^a-z0-9_-]+/gi, '-')}`
}
