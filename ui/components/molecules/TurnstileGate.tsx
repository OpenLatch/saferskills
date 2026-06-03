import { useEffect, useId, useRef, useState } from 'react'

// ── Minimal Cloudflare Turnstile typing ─────────────────────────────────────
// The explicit-render API attaches `window.turnstile` once the script loads.
interface TurnstileRenderOptions {
  sitekey: string
  callback: (token: string) => void
  'expired-callback'?: () => void
  'error-callback'?: () => void
  appearance?: 'always' | 'execute' | 'interaction-only' | 'managed'
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
  /** Auto-proceed: fired the instant the widget returns a token. */
  onVerified: (token: string) => void
  /** Escape / backdrop / Cancel button — the host closes + clears its pending action. */
  onCancel: () => void
}

/**
 * Human-verification modal gating a scan submission. Built on the native
 * `<dialog>` element (free focus-trap / Escape / focus-restore — same platform
 * base as `Dialog.tsx`, but NOT that component: its confirm/cancel contract has
 * no slot for a third-party widget). The Cloudflare Turnstile widget renders
 * inside on first open and **auto-proceeds** the moment it returns a token.
 *
 * CSS is DS-owned in `ui/styles/components.css` (`.turnstile-gate*`); the enter
 * animation short-circuits under `prefers-reduced-motion`.
 */
export default function TurnstileGate({ open, siteKey, onVerified, onCancel }: Props) {
  const dialogRef = useRef<HTMLDialogElement | null>(null)
  const containerRef = useRef<HTMLDivElement | null>(null)
  const widgetIdRef = useRef<string | null>(null)
  const headingId = useId()
  const [retry, setRetry] = useState(false)

  // Hold the latest onVerified without re-rendering the widget on every change.
  const onVerifiedRef = useRef(onVerified)
  onVerifiedRef.current = onVerified

  useEffect(() => {
    const dialog = dialogRef.current
    if (!dialog) return

    if (!open) {
      if (dialog.open) dialog.close()
      // Reset so a subsequent open issues a fresh, unused challenge.
      if (widgetIdRef.current !== null) window.turnstile?.reset(widgetIdRef.current)
      return
    }

    if (!dialog.open) dialog.showModal()
    setRetry(false)
    let cancelled = false
    loadTurnstile()
      .then(() => {
        // Read the live global (not the promise's resolved value) — window.turnstile
        // is the canonical singleton the script attaches.
        const turnstile = window.turnstile
        if (cancelled || !containerRef.current || !turnstile) return
        if (widgetIdRef.current !== null) {
          // Already rendered (re-open) — reset for a fresh single-use token.
          turnstile.reset(widgetIdRef.current)
          return
        }
        // expired + error share one recovery: show retry copy + reset for a
        // fresh challenge.
        const onWidgetFail = () => {
          setRetry(true)
          if (widgetIdRef.current !== null) turnstile.reset(widgetIdRef.current)
        }
        widgetIdRef.current = turnstile.render(containerRef.current, {
          sitekey: siteKey,
          appearance: 'managed',
          callback: (token: string) => onVerifiedRef.current(token),
          'expired-callback': onWidgetFail,
          'error-callback': onWidgetFail,
        })
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
      aria-labelledby={headingId}
      onCancel={onCancel}
      onClick={(e) => {
        if (e.target === dialogRef.current) onCancel()
      }}
    >
      <h3 id={headingId}>Verify you're human</h3>
      <p className="tg-sub">One quick check before we start the scan.</p>
      <div className="tg-widget" ref={containerRef} />
      {retry && (
        <p className="tg-retry" role="alert">
          That check didn't go through. Complete it above to continue.
        </p>
      )}
      <div className="tg-actions">
        <button type="button" className="btn paper sm" onClick={onCancel}>
          Cancel
        </button>
      </div>
    </dialog>
  )
}
