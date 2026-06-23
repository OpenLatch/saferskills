import { Command } from 'cmdk'
import { useEffect, useId, useLayoutEffect, useMemo, useRef, useState } from 'react'
import type { RefObject } from 'react'
import SearchDropdownItem, { type SearchHit } from './SearchDropdownItem'

export interface SearchGroup {
  kind: string
  label: string
  hits: SearchHit[]
}

/** Hard ceiling on the dropdown's height. Below this the dropdown
 *  scrolls internally; we never let it grow above this even on
 *  large viewports. */
const HARD_MAX_HEIGHT_PX = 440

/** Safety margin between the dropdown and the viewport bottom —
 *  keeps the list from sliding under a marquee, footer, or fold. */
const BOTTOM_GUTTER_PX = 24

/** Minimum the dropdown will ever shrink to. On very short viewports
 *  we'd rather show a scrollable mini-list than nothing. */
const MIN_HEIGHT_PX = 200

interface Props {
  /** Live query string from the host input. */
  query: string
  /** Ref to the host input — used for ARIA wiring + outside-click detection. */
  inputRef: RefObject<HTMLInputElement | null>
  /** Async search; must return groups already filtered + sorted. AbortController fires on rapid retype. */
  search: (query: string, signal?: AbortSignal) => Promise<SearchGroup[]>
  /** Activated when the user picks a row (mouse or Enter). */
  onSelect: (hit: SearchHit) => void
  /** Where to send the user when they hit Enter with no row selected. */
  fallbackHref?: (query: string) => string
  /** Optional element whose TOP edge acts as the dropdown's floor.
   *  When set, the dropdown's max-height stops at this boundary (minus a
   *  small gutter) instead of running to the viewport bottom. Use this to
   *  keep the panel above a marquee, footer band, or fold. */
  bottomBoundaryRef?: RefObject<HTMLElement | null>
}

const DEBOUNCE_MS = 300

/**
 * Sentinel "nothing is active" value for cmdk's controlled `value`.
 *
 * cmdk auto-highlights the first item whenever its internal value is falsy
 * (`n.current.value || selectFirstItem()` in its item-registration path). We
 * want the Linear/Algolia model — nothing highlighted until the user presses ↓
 * — so we seed the controlled value with a non-empty token that matches no
 * item (every real value is `${kind}:${slug}`, which always contains a colon,
 * so a colon-free sentinel can never collide). The arrow/Enter handler already
 * treats a non-matching value as "no active row" (its `indexOf` is `-1`).
 */
const NO_ACTIVE = '__none__'

type LoadState =
  | { phase: 'idle' }
  | { phase: 'loading' }
  | { phase: 'ready'; groups: SearchGroup[] }
  | { phase: 'error' }

/**
 * Inline command-palette dropdown anchored below a search input.
 *
 * Generic over the data source — the consumer passes a `search` callback
 * so the molecule has no coupling to the catalog repository (mock JSON
 * initially, HTTP once `/api/v1/catalog/search` ships).
 *
 * Behaviour
 * ─────────────────────────────────────────────────────────────────────
 * The dropdown is closed until the query has at least one character —
 * focus alone does not open it. This keeps the hero clean and matches
 * the muscle memory of Linear / Vercel / Algolia DocSearch, where
 * suggestions are reserved for typed intent.
 *
 * Animations
 * ─────────────────────────────────────────────────────────────────────
 * Open: `clip-path` reveal + 6px translateY drop + opacity, 180ms,
 * `ease-out-expo`. Pure CSS — no JS height measurement. Reduced-motion
 * collapses to a 100ms opacity fade. See ui/styles/components.css.
 *
 * Owns
 * ─────────────────────────────────────────────────────────────────────
 *   - debounced fetch with AbortController
 *   - cmdk listbox semantics (ArrowDown/Up, Enter, Escape)
 *   - aria-activedescendant wiring back onto the host input
 *   - loading / ready / no-results / error UI states
 */
export default function SearchDropdown({
  query,
  inputRef,
  search,
  onSelect,
  fallbackHref,
  bottomBoundaryRef,
}: Props) {
  const listboxId = useId()
  const [state, setState] = useState<LoadState>({ phase: 'idle' })
  const [activeValue, setActiveValue] = useState<string>(NO_ACTIVE)
  // Escape dismisses the panel even though the query still has text. Sticky
  // until the user re-engages the field (focus), so the dropdown closes on Esc
  // (the requested behaviour) without clearing what they typed.
  const [dismissed, setDismissed] = useState(false)
  const wrapperRef = useRef<HTMLDivElement>(null)

  const q = query.trim()
  const open = q.length > 0 && !dismissed

  // The result set in the order it renders. cmdk owns the `data-selected`
  // highlight + `aria-activedescendant` via the controlled `value` prop, but
  // the real <input> is an external sibling of <Command>, so cmdk's own
  // keydown navigation never reaches it. We supply that navigation ourselves
  // and need the visible hits flattened to a roving list (parallel arrays:
  // `flatValues[i]` is the cmdk value key for `flatHits[i]`).
  const readyGroups = state.phase === 'ready' ? state.groups : null
  const { flatHits, flatValues } = useMemo(() => {
    const hits = (readyGroups ?? []).flatMap((g) => g.hits)
    return {
      flatHits: hits,
      flatValues: hits.map((h) => `${h.kind}:${h.slug}`),
    }
  }, [readyGroups])

  // Clamp max-height against either the explicit bottom boundary (e.g. a
  // marquee band) or the visual viewport — whichever is closer. The
  // result is published as a CSS custom property so the styling stays
  // in ui/styles/components.css.
  useLayoutEffect(() => {
    if (!open) return
    const wrapper = wrapperRef.current
    const input = inputRef.current
    if (!wrapper || !input) return

    function recompute() {
      if (!wrapper || !input) return
      const inputRect = input.getBoundingClientRect()
      const viewportHeight = window.visualViewport?.height ?? window.innerHeight
      // Floor = either the boundary's top edge, or the viewport bottom.
      // Take the lower of the two — whichever the dropdown would hit first.
      const boundary = bottomBoundaryRef?.current
      const floor = boundary
        ? Math.min(boundary.getBoundingClientRect().top, viewportHeight)
        : viewportHeight
      // 6px = the visual gap we leave between input bottom and dropdown top.
      const available = floor - inputRect.bottom - 6 - BOTTOM_GUTTER_PX
      const clamped = Math.max(
        MIN_HEIGHT_PX,
        Math.min(HARD_MAX_HEIGHT_PX, available),
      )
      wrapper.style.setProperty('--search-dropdown-max-h', `${clamped}px`)
    }

    recompute()
    window.addEventListener('resize', recompute)
    window.addEventListener('scroll', recompute, { passive: true })
    window.visualViewport?.addEventListener('resize', recompute)
    return () => {
      window.removeEventListener('resize', recompute)
      window.removeEventListener('scroll', recompute)
      window.visualViewport?.removeEventListener('resize', recompute)
    }
  }, [open, inputRef, bottomBoundaryRef])

  // Outside-click closes by blurring the host input
  useEffect(() => {
    if (!open) return
    const onPointerDown = (e: PointerEvent) => {
      const target = e.target as Node | null
      if (!target) return
      if (wrapperRef.current?.contains(target)) return
      if (inputRef.current?.contains(target)) return
      inputRef.current?.blur()
    }
    document.addEventListener('pointerdown', onPointerDown)
    return () => document.removeEventListener('pointerdown', onPointerDown)
  }, [open, inputRef])

  // Escape closes the dropdown (clears any highlight) + blurs the input so the
  // typewriter loop resumes. `dismissed` keeps it closed until the user
  // re-engages the field — see the focus effect below.
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return
      e.preventDefault()
      setActiveValue(NO_ACTIVE)
      setDismissed(true)
      inputRef.current?.blur()
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [open, inputRef])

  // Re-engaging the field (focus) lifts an Escape dismissal, so the dropdown
  // reopens with the text still present.
  useEffect(() => {
    const input = inputRef.current
    if (!input) return
    const onFocus = () => setDismissed(false)
    input.addEventListener('focus', onFocus)
    return () => input.removeEventListener('focus', onFocus)
  }, [inputRef])

  // Keyboard navigation on the host input — the navigation cmdk can't receive
  // because the input is an external sibling, not its <Command.Input>:
  //   ↑/↓  move the active row (wrap at both ends, mirroring cmdk's `loop`)
  //   Enter open the highlighted hit, else fall back to full-catalog search
  // No preselection (Linear/Algolia model): nothing is active until ↓. Esc is
  // owned by the dedicated effect above; Home/End/Tab are left to text editing.
  useEffect(() => {
    const input = inputRef.current
    if (!input) return
    const onKey = (e: KeyboardEvent) => {
      // -1 when nothing is highlighted (the NO_ACTIVE sentinel, or a value
      // left over from an earlier query that's no longer in the list).
      const i = flatValues.indexOf(activeValue)
      if (e.key === 'ArrowDown') {
        if (flatValues.length === 0) return
        e.preventDefault()
        const next = i < 0 || i === flatValues.length - 1 ? 0 : i + 1
        setActiveValue(flatValues[next])
      } else if (e.key === 'ArrowUp') {
        if (flatValues.length === 0) return
        e.preventDefault()
        const prev = i <= 0 ? flatValues.length - 1 : i - 1
        setActiveValue(flatValues[prev])
      } else if (e.key === 'Enter') {
        if (i >= 0) {
          e.preventDefault()
          onSelect(flatHits[i])
          return
        }
        // Nothing highlighted → keep the full-catalog-search fallback.
        const trimmed = query.trim()
        if (trimmed && fallbackHref) {
          e.preventDefault()
          window.location.assign(fallbackHref(trimmed))
        }
      }
    }
    input.addEventListener('keydown', onKey)
    return () => input.removeEventListener('keydown', onKey)
  }, [flatValues, flatHits, activeValue, query, fallbackHref, onSelect, inputRef])

  // Clear a stale highlight whenever the result set changes (new query, retry)
  // — a value active under an earlier query must not survive into fresh hits.
  // Reset to the sentinel (not ''), so cmdk still won't auto-highlight row 0.
  useEffect(() => {
    setActiveValue(NO_ACTIVE)
  }, [readyGroups])

  // Keep the active row visible — the list scrolls internally above 440px.
  useEffect(() => {
    if (!activeValue) return
    const wrapper = wrapperRef.current
    if (!wrapper) return
    const reduce =
      typeof window !== 'undefined' &&
      window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
    const raf = requestAnimationFrame(() => {
      const el = wrapper.querySelector<HTMLElement>("[data-selected='true']")
      el?.scrollIntoView({ block: 'nearest', behavior: reduce ? 'auto' : 'smooth' })
    })
    // Cancel a pending frame when activeValue changes again (rapid/held arrows)
    // so we never stack scrolls toward a row that's already been superseded.
    return () => cancelAnimationFrame(raf)
  }, [activeValue])

  // Debounced fetch
  useEffect(() => {
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
  }, [q, search])

  // ARIA wiring on the host input
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
    // Only point at a row that actually exists — never at the NO_ACTIVE
    // sentinel (which renders no option element).
    if (!open || !flatValues.includes(activeValue)) {
      input.removeAttribute('aria-activedescendant')
      return
    }
    input.setAttribute('aria-activedescendant', toOptionId(listboxId, activeValue))
  }, [activeValue, flatValues, open, listboxId, inputRef])

  if (!open) return null

  const groups = state.phase === 'ready' ? state.groups : []
  const hitCount = groups.reduce((sum, g) => sum + g.hits.length, 0)

  return (
    <div ref={wrapperRef} className="search-dropdown" role="presentation" data-state="open">
      <Command
        shouldFilter={false}
        value={activeValue}
        // Mouse hover routes through here (cmdk sets the hovered row's value).
        // Coerce cmdk's own falsy resets (it emits '' while tearing the old
        // result set down on a requery) back to the sentinel — a falsy value
        // would re-arm cmdk's "auto-highlight the first item" on the next
        // registration, breaking the no-preselect contract.
        onValueChange={(v) => setActiveValue(v || NO_ACTIVE)}
        loop
        label="Catalog search"
      >
        <Command.List id={listboxId}>
          {state.phase === 'loading' && <LoadingSkeleton />}
          {state.phase === 'error' && (
            <ErrorState
              onRetry={() => {
                setState({ phase: 'loading' })
                search(q)
                  .then((groups) => setState({ phase: 'ready', groups }))
                  .catch(() => setState({ phase: 'error' }))
              }}
            />
          )}
          {state.phase === 'ready' &&
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
          {state.phase === 'ready' && hitCount === 0 && <NoResults query={q} />}
        </Command.List>
      </Command>
    </div>
  )
}

/** Skeleton rows that mirror the real result layout — name block,
 *  editor block, severity-pill block. Shimmer is cross-fade only,
 *  reduced-motion disables the animation in CSS. */
function LoadingSkeleton() {
  return (
    <div className="search-dropdown-skel-group" aria-busy="true" aria-live="polite">
      <div className="search-dropdown-skel-heading" />
      <div className="search-dropdown-skel-row">
        <span className="skel skel-name" />
        <span className="skel skel-editor" />
        <span className="skel skel-pill" />
      </div>
      <div className="search-dropdown-skel-row">
        <span className="skel skel-name skel-narrow" />
        <span className="skel skel-editor" />
        <span className="skel skel-pill" />
      </div>
      <div className="search-dropdown-skel-row">
        <span className="skel skel-name" />
        <span className="skel skel-editor" />
        <span className="skel skel-pill" />
      </div>
    </div>
  )
}

function NoResults({ query }: { query: string }) {
  return (
    <div className="search-dropdown-noresult" role="status">
      <span className="search-dropdown-noresult-glyph" aria-hidden="true">
        <svg viewBox="0 0 24 24" width="22" height="22">
          <title>No results</title>
          <circle cx="11" cy="11" r="7" />
          <path d="m20 20-3.5-3.5" />
          <path d="M8 14l6-6M14 14l-6-6" />
        </svg>
      </span>
      <div className="search-dropdown-noresult-body">
        <p className="search-dropdown-noresult-title">
          No matches for <span className="q">&ldquo;{query}&rdquo;</span>
        </p>
        <p className="search-dropdown-noresult-hint">
          Press <kbd className="kbd-chip">↵</kbd> to search the full catalog.
        </p>
      </div>
    </div>
  )
}

function ErrorState({ onRetry }: { onRetry: () => void }) {
  return (
    <div className="search-dropdown-error" role="alert">
      <span>Search failed.</span>
      <button type="button" className="search-dropdown-retry" onClick={onRetry}>
        Retry
      </button>
    </div>
  )
}

function toOptionId(listboxId: string, value: string): string {
  return `${listboxId}-opt-${value.replace(/[^a-z0-9_-]+/gi, '-')}`
}
