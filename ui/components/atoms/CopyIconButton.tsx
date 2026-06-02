import { useEffect, useRef, useState } from 'react'

interface Props {
  /** The full string written to the clipboard (e.g. the untruncated sha256). */
  value: string
  /** Accessible label / tooltip for the idle state. */
  label?: string
}

function CopyGlyph() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
      <rect x="9" y="9" width="11" height="11" rx="1" />
      <path d="M5 15V5a1 1 0 0 1 1-1h9" />
    </svg>
  )
}

function CheckGlyph() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" aria-hidden="true">
      <path d="M5 12.5 10 17.5 19 6.5" />
    </svg>
  )
}

/**
 * Discreet icon-only click-to-copy button. Flips to a check for ~1.2s on success
 * — self-contained (no global Toast dependency), so it drops in anywhere (a sha
 * next to a label, a scan id, …). Token-styled via `.copy-icon` in
 * `ui/styles/components.css`. NOT the hex `Button` — deliberately minimal.
 */
export default function CopyIconButton({ value, label = 'Copy' }: Props) {
  const [copied, setCopied] = useState(false)
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(
    () => () => {
      if (timer.current) clearTimeout(timer.current)
    },
    []
  )

  async function copy() {
    try {
      await navigator.clipboard.writeText(value)
      setCopied(true)
      if (timer.current) clearTimeout(timer.current)
      timer.current = setTimeout(() => setCopied(false), 1200)
    } catch {
      /* clipboard unavailable — no-op (the value stays selectable in the DOM) */
    }
  }

  return (
    <button
      type="button"
      className={`copy-icon${copied ? ' is-copied' : ''}`}
      onClick={copy}
      aria-label={copied ? 'Copied' : label}
      title={copied ? 'Copied' : label}
    >
      {copied ? <CheckGlyph /> : <CopyGlyph />}
    </button>
  )
}
