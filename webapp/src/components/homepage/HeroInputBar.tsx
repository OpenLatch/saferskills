import Kbd from '@ui/components/atoms/Kbd'
import { useEffect, useRef, useState } from 'react'
import { useHeroShortcut } from '@/lib/use-hero-shortcut'
import { formatShortcut, useIsMac } from '@/lib/use-platform-shortcut'
import HeroSearchDropdown from './HeroSearchDropdown'

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
      <title>Link</title>
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
 * Loop:
 *   1. Hold the initial placeholder for 3.5s (matches the mockup's `init`).
 *   2. Erase it char-by-char (28ms / char).
 *   3. Gap of 360ms — caret briefly visible and blinking.
 *   4. Type the next word (55ms / char + 0-26ms jitter to feel human).
 *   5. Hold 1600ms, then back to step 2.
 *
 * Focus pauses the loop and clears the placeholder; blur resumes it
 * (only if the user didn't leave a value behind). `prefers-reduced-motion`
 * short-circuits the effect so the field just shows the initial placeholder.
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
  const isMac = useIsMac()

  useHeroShortcut({ key: shortcutKey ?? '', ref: inputRef })

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

  function handleSelect(slug: string) {
    window.location.assign(`/items/${slug}`)
  }

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
      {shortcutKey && (
        <span className="p1-kbd-host" aria-hidden="true">
          <Kbd>{formatShortcut(shortcutKey, isMac)}</Kbd>
        </span>
      )}
      <button className="p1-enter" type="button" aria-label={submitAriaLabel}>
        <span className="key">↵</span>
      </button>
    </div>
  )

  if (!showDropdown) return inputBar

  return (
    <div className="p1-search">
      {inputBar}
      <HeroSearchDropdown query={value} inputRef={inputRef} onSelect={handleSelect} />
    </div>
  )
}
