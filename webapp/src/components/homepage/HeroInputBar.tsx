import Kbd from '@ui/components/atoms/Kbd'
import SearchDropdown, { type SearchGroup } from '@ui/components/molecules/SearchDropdown'
import { useFocusShortcut } from '@ui/hooks/use-focus-shortcut'
import { formatShortcut, useIsMac } from '@ui/hooks/use-platform-shortcut'
import { useCallback, useEffect, useRef, useState } from 'react'
import { groupByKind, KIND_LABELS, searchCatalog } from '@/lib/catalog-search'

type Kind = 'find' | 'scan'

interface Props {
  kind: Kind
  /** First placeholder rendered server-side. Also the first entry the
   *  typewriter erases after the initial hold — keep in sync with WORDS. */
  initialPlaceholder: string
  ariaLabel: string
  submitAriaLabel: string
  /** Single character (e.g. 'k', 'j'). When set, Cmd/Ctrl+<key> focuses
   *  the input from anywhere on the page. */
  shortcutKey?: string
}

/**
 * Rotating-placeholder words per card kind. The first entry MUST match the
 * `initialPlaceholder` prop passed from `webapp/src/pages/index.astro` — the
 * typewriter starts in "holding" mode at the end of words[0] so the SSR
 * placeholder is the first thing it erases, with no flash-of-empty-state.
 */
const WORDS: Record<Kind, readonly string[]> = {
  find: [
    'ripgrep, supabase, linear...',
    'claude-pdf',
    'github-mcp',
    'slack-bot',
    'linear-mcp',
    'obsidian-mcp',
    'notion-mcp',
  ],
  scan: [
    'github.com/anthropic/claude-mcp',
    'github.com/acme/agent-skill',
    'github.com/openlatch/saferskills',
    'github.com/modelcontextprotocol/servers',
  ],
}

const ICONS: Record<Kind, React.ReactElement> = {
  find: (
    <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
      <title>Search</title>
      <circle cx="11" cy="11" r="7" />
      <path d="m20 20-3.5-3.5" />
    </svg>
  ),
  scan: (
    <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
      <title>Scan</title>
      <path d="M10 13a5 5 0 0 0 7.07 0l3-3a5 5 0 1 0-7.07-7.07l-1.5 1.5" />
      <path d="M14 11a5 5 0 0 0-7.07 0l-3 3a5 5 0 1 0 7.07 7.07l1.5-1.5" />
    </svg>
  ),
}

// Pacing (ms). GAP_MS = 2 × the caret's 1.05s blink cycle so the user sees
// two full blinks between words before the next one types in.
const TYPE_MS = 55
const ERASE_MS = 28
const HOLD_MS = 1600
const GAP_MS = 2100
const INIT_DELAY_MS = 3500
const PAUSED_POLL_MS = 400

/**
 * Hero search/scan input with typewriter placeholder animation.
 *
 * Renders the icon + caret + input + Enter affordance as a single React
 * island so the animation owns its own DOM (no race with ActionCard's
 * `client:visible` hydration). The CSS already in `page-home.css` drives:
 *   - `.p1-input.has-value .caret { display: none }` — caret hides whenever
 *     the field shows anything (typed value OR placeholder text).
 *   - `@keyframes p1-blink` — the 1.05s caret blink between words.
 *
 * For the `find` variant, the bar composes the DS-side `SearchDropdown`
 * molecule (cmdk-driven listbox) anchored below the input. The dropdown is
 * generic — we adapt our catalog-search lib via a memoised callback so the
 * molecule has zero coupling to this page.
 */
export default function HeroInputBar({
  kind,
  initialPlaceholder,
  ariaLabel,
  submitAriaLabel,
  shortcutKey,
}: Props) {
  const [placeholder, setPlaceholder] = useState(initialPlaceholder)
  const [value, setValue] = useState('')
  const focusedRef = useRef(false)
  const valueRef = useRef(value)
  valueRef.current = value
  const inputRef = useRef<HTMLInputElement>(null)
  // The marquee band sits at the bottom of the hero and is rendered by
  // Astro outside this React island. We discover it via DOM query at
  // mount time so the dropdown can clamp its height against the
  // marquee's top edge instead of the viewport bottom.
  const bottomBoundaryRef = useRef<HTMLElement | null>(null)
  const isMac = useIsMac()

  useFocusShortcut({ key: shortcutKey ?? '', ref: inputRef })

  useEffect(() => {
    if (typeof document === 'undefined') return
    bottomBoundaryRef.current = document.querySelector<HTMLElement>('.supported-band')
  }, [])

  useEffect(() => {
    if (typeof window === 'undefined') return
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return

    const words = WORDS[kind]
    let wordIndex = 0
    let charIndex = words[0].length
    let mode: 'typing' | 'holding' | 'erasing' = 'holding'
    let timer: ReturnType<typeof setTimeout> | null = null
    let alive = true

    function step() {
      if (!alive) return
      if (focusedRef.current || valueRef.current) {
        timer = setTimeout(step, PAUSED_POLL_MS)
        return
      }
      const w = words[wordIndex]
      if (mode === 'typing') {
        charIndex++
        setPlaceholder(w.slice(0, charIndex))
        if (charIndex >= w.length) {
          mode = 'holding'
          timer = setTimeout(step, HOLD_MS)
          return
        }
        timer = setTimeout(step, TYPE_MS + Math.random() * 26)
      } else if (mode === 'holding') {
        mode = 'erasing'
        timer = setTimeout(step, ERASE_MS)
      } else {
        charIndex--
        setPlaceholder(w.slice(0, Math.max(0, charIndex)))
        if (charIndex <= 0) {
          wordIndex = (wordIndex + 1) % words.length
          mode = 'typing'
          timer = setTimeout(step, GAP_MS)
        } else {
          timer = setTimeout(step, ERASE_MS)
        }
      }
    }

    timer = setTimeout(step, INIT_DELAY_MS)
    return () => {
      alive = false
      if (timer) clearTimeout(timer)
    }
  }, [kind])

  const hasValue = !!value || !!placeholder
  const showDropdown = kind === 'find'

  const search = useCallback(async (q: string, signal?: AbortSignal): Promise<SearchGroup[]> => {
    const hits = await searchCatalog(q, signal)
    return groupByKind(hits).map((g) => ({
      kind: g.kind,
      label: KIND_LABELS[g.kind],
      hits: g.hits,
    }))
  }, [])

  const handleSelect = useCallback((hit: { slug: string }) => {
    window.location.assign(`/items/${hit.slug}`)
  }, [])

  const inputBar = (
    <div className={`p1-input${hasValue ? ' has-value' : ''}`}>
      <span className="p1-icon" aria-hidden="true">
        {ICONS[kind]}
      </span>
      <label className="p1-field">
        <span className="caret" aria-hidden="true" />
        <input
          ref={inputRef}
          type="text"
          autoComplete="off"
          aria-label={ariaLabel}
          placeholder={placeholder}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onFocus={() => {
            focusedRef.current = true
            setPlaceholder('')
          }}
          onBlur={() => {
            focusedRef.current = false
          }}
        />
      </label>
      <button
        type="button"
        className="p1-submit"
        aria-label={submitAriaLabel}
        onClick={() => inputRef.current?.focus()}
      >
        {shortcutKey ? (
          <Kbd>{formatShortcut(shortcutKey, isMac)}</Kbd>
        ) : (
          <span className="p1-submit-ret" aria-hidden="true">
            ↵
          </span>
        )}
      </button>
    </div>
  )

  if (!showDropdown) return inputBar

  return (
    <div className="search-anchor">
      {inputBar}
      <SearchDropdown
        query={value}
        inputRef={inputRef}
        search={search}
        onSelect={handleSelect}
        bottomBoundaryRef={bottomBoundaryRef}
        fallbackHref={(q) => `/capabilities?q=${encodeURIComponent(q)}`}
      />
    </div>
  )
}
