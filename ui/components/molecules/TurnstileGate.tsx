import { useEffect, useId, useRef, useState } from 'react'
import Button from '../atoms/Button'

// ── Minimal Cloudflare Turnstile typing ─────────────────────────────────────
// The explicit-render API attaches `window.turnstile` once the script loads.
interface TurnstileRenderOptions {
  sitekey: string
  callback: (token: string) => void
  'expired-callback'?: () => void
  'error-callback'?: () => void
  // NB: `appearance` is NOT the widget mode. Valid values are only
  // 'always' | 'execute' | 'interaction-only' (default 'always'). The
  // managed/non-interactive/invisible *mode* is set in the Cloudflare
  // dashboard — passing it here makes `render()` throw. (Do not re-add 'managed'.)
  appearance?: 'always' | 'execute' | 'interaction-only'
  theme?: 'auto' | 'light' | 'dark'
}
interface TurnstileApi {
  render: (el: HTMLElement, opts: TurnstileRenderOptions) => string
  reset: (widgetId?: string) => void
  remove: (widgetId?: string) => void
}
declare global {
  interface Window {
    turnstile?: TurnstileApi
  }
}

const SCRIPT_SRC = 'https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit'

// Motion timings — mirrored by the `.turnstile-gate` keyframes in components.css.
const EXIT_MS = 160
// How long the "Verified" beat stays up before the host proceeds. Shortened (not
// removed) under reduced motion — the acknowledgement is informational, the draw
// is the part that's motion.
const SUCCESS_HOLD_MS = 750
const SUCCESS_HOLD_REDUCED_MS = 250

const prefersReducedMotion = (): boolean =>
  typeof window !== 'undefined' &&
  typeof window.matchMedia === 'function' &&
  window.matchMedia('(prefers-reduced-motion: reduce)').matches

// Module-level singleton: inject the Turnstile script at most once across every
// gate instance + open. Cached promise resolves to `window.turnstile`.
let loadPromise: Promise<TurnstileApi> | null = null

function loadTurnstile(): Promise<TurnstileApi> {
  if (loadPromise) return loadPromise
  loadPromise = new Promise<TurnstileApi>((resolve, reject) => {
    if (typeof window === 'undefined') {
      reject(new Error('turnstile: no window'))
      return
    }
    if (window.turnstile) {
      resolve(window.turnstile)
      return
    }
    const script = document.createElement('script')
    script.src = SCRIPT_SRC
    script.async = true
    script.defer = true
    script.onload = () => {
      if (window.turnstile) resolve(window.turnstile)
      else reject(new Error('turnstile: script loaded but window.turnstile missing'))
    }
    script.onerror = () => {
      // Let a later open retry the injection.
      loadPromise = null
      reject(new Error('turnstile: script failed to load'))
    }
    document.head.appendChild(script)
  })
  return loadPromise
}

interface Props {
  /** Show the modal + render the widget. The host owns this. */
  open: boolean
  /** Cloudflare Turnstile site key (passed in — `ui/` never reads env). */
  siteKey: string
  /** Auto-proceed: fired (after a brief "Verified" beat) once the widget returns a token. */
  onVerified: (token: string) => void
  /** Escape / backdrop / Cancel button — the host closes + clears its pending action. */
  onCancel: () => void
}

/** loading → the Cloudflare widget is mounting; live → its UI is showing;
 *  success → a token arrived (the "Verified" beat before the host proceeds). */
type Phase = 'loading' | 'live' | 'success'

/**
 * Human-verification modal gating a scan submission. Built on the native
 * `<dialog>` element (free focus-trap / Escape / focus-restore — same platform
 * base as `Dialog.tsx`, but NOT that component: its confirm/cancel contract has
 * no slot for a third-party widget). The Cloudflare Turnstile widget renders
 * inside (managed widget mode is set in the dashboard, not via `appearance`)
 * and the gate **auto-proceeds** the moment it returns a token.
 *
 * Chrome is DS-owned: hairline border + `--shadow-overlay` ambient lift over a
 * dimmed, blurred `::backdrop` (NO brutalist `--shadow-stamp`). The framed widget
 * slot shows a teal scan-line "verifying" state so managed mode never looks empty,
 * and a drawn check on success. Enter (scale-fade + staggered rows) and the faster
 * exit are CSS keyframes, every motion short-circuited under prefers-reduced-motion.
 */
export default function TurnstileGate({ open, siteKey, onVerified, onCancel }: Props) {
  const dialogRef = useRef<HTMLDialogElement | null>(null)
  const containerRef = useRef<HTMLDivElement | null>(null)
  const widgetIdRef = useRef<string | null>(null)
  const headingId = useId()
  const [phase, setPhase] = useState<Phase>('loading')
  const [retry, setRetry] = useState(false)
  const [closing, setClosing] = useState(false)

  // Hold the latest onVerified without re-rendering the widget on every change.
  const onVerifiedRef = useRef(onVerified)
  onVerifiedRef.current = onVerified

  // Pending timeouts (success beat / exit close) — cleared on re-open + unmount.
  const timers = useRef<number[]>([])
  const clearTimers = () => {
    for (const t of timers.current) clearTimeout(t)
    timers.current = []
  }
  const later = (fn: () => void, ms: number) => {
    timers.current.push(window.setTimeout(fn, ms))
  }

  // Clear any pending timers if the component unmounts mid-beat.
  useEffect(() => clearTimers, [])

  useEffect(() => {
    const dialog = dialogRef.current
    if (!dialog) return

    if (!open) {
      // Cancel any pending success-beat handoff — a cancel during the
      // "Verified" hold must never let onVerified fire after the gate closed.
      clearTimers()
      // Reset so a subsequent open issues a fresh, unused challenge.
      if (widgetIdRef.current !== null) window.turnstile?.reset(widgetIdRef.current)
      if (!dialog.open) return
      // Animate out, then close (skip the movement under reduced motion).
      if (prefersReducedMotion()) {
        dialog.close()
      } else {
        setClosing(true)
        later(() => {
          setClosing(false)
          dialog.close()
        }, EXIT_MS)
      }
      return
    }

    // Opening — fresh state, fresh challenge.
    clearTimers()
    setClosing(false)
    setPhase('loading')
    setRetry(false)
    if (!dialog.open) dialog.showModal()

    let cancelled = false
    loadTurnstile()
      .then(() => {
        // Read the live global (not the promise's resolved value) — window.turnstile
        // is the canonical singleton the script attaches.
        const turnstile = window.turnstile
        if (cancelled || !containerRef.current || !turnstile) return
        // expired + error share one recovery: show retry copy + reset for a
        // fresh challenge.
        const onWidgetFail = () => {
          setRetry(true)
          if (widgetIdRef.current !== null) turnstile.reset(widgetIdRef.current)
        }
        // token → "Verified" beat, then hand the token to the host.
        const onToken = (token: string) => {
          setPhase('success')
          later(
            () => onVerifiedRef.current(token),
            prefersReducedMotion() ? SUCCESS_HOLD_REDUCED_MS : SUCCESS_HOLD_MS
          )
        }
        if (widgetIdRef.current !== null) {
          // Already rendered (re-open) — reset for a fresh single-use token.
          turnstile.reset(widgetIdRef.current)
          setPhase('live')
          return
        }
        widgetIdRef.current = turnstile.render(containerRef.current, {
          sitekey: siteKey,
          // No `appearance` override — default 'always' renders the widget; the
          // managed/invisible behavior is the dashboard widget mode. Passing
          // appearance:'managed' here threw "Unknown appearance value" and broke
          // the whole gate.
          callback: onToken,
          'expired-callback': onWidgetFail,
          'error-callback': onWidgetFail,
        })
        setPhase('live')
      })
      .catch(() => setRetry(true))

    return () => {
      cancelled = true
    }
  }, [open, siteKey])

  return (
    // biome-ignore lint/a11y/useKeyWithClickEvents: backdrop dismiss supplements Esc + the Cancel button; the dialog is keyboard-complete
    <dialog
      ref={dialogRef}
      className="turnstile-gate"
      data-closing={closing ? '' : undefined}
      aria-labelledby={headingId}
      onCancel={onCancel}
      onClick={(e) => {
        if (e.target === dialogRef.current) onCancel()
      }}
    >
      <span className="tg-accent" aria-hidden="true" />
      <div className="tg-head">
        <span className="tg-eyebrow">Security · Human check</span>
        <h3 id={headingId}>Verify you're human</h3>
      </div>
      <p className="tg-sub">
        One quick check before we start the scan. No account, nothing stored.
      </p>
      <div className="tg-frame" data-phase={phase}>
        <div className="tg-widget" ref={containerRef} />
        <div className="tg-overlay tg-loading" aria-hidden="true">
          <span className="tg-scan" />
          <span className="tg-spin" />
          <span className="tg-ov-label">Verifying you're human…</span>
        </div>
        <div className="tg-overlay tg-done" aria-hidden="true">
          <span className="tg-check">
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <path d="M5 13l4 4L19 7" />
            </svg>
          </span>
          <span className="tg-ov-label">Verified — starting your scan…</span>
        </div>
      </div>
      {/* Polite status for screen readers — the overlays themselves are decorative. */}
      <span className="sr-only" aria-live="polite">
        {phase === 'success'
          ? 'Verified. Starting your scan.'
          : phase === 'loading'
            ? 'Verifying you are human.'
            : ''}
      </span>
      {retry && (
        <p className="tg-retry" role="alert">
          That check didn't go through. Complete it above to continue.
        </p>
      )}
      <div className="tg-actions">
        <Button variant="ghost" size="sm" type="button" onClick={onCancel}>
          Cancel
        </Button>
      </div>
    </dialog>
  )
}
