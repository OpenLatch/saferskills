import { useEffect, useRef, useState } from 'react'

interface Props {
  /** Initial value (e.g. parsed from a query string). */
  initialValue?: string
  /** Label for the submit button. */
  submitLabel?: string
  /** Submission handler. Returns a `Promise<void>` so callers can show loading state. */
  onSubmit?: (githubUrl: string) => Promise<void> | void
  /** Error to render below the input (passed in from the page after a failed submit). */
  error?: string | null
  /** Disabled while a parent flow is in-flight. */
  disabled?: boolean
}

/**
 * Big `github.com/` prefixed input used on /scan and the homepage AUDIT card.
 * Vocabulary: `.scan-input` from `mockups/hifi/app-pages.css`. The prefix is a
 * non-editable inline label; the editable region accepts `<org>/<repo>` or a
 * full URL. The submit button is a hex CTA.
 */
export default function ScanInput({
  initialValue = '',
  submitLabel = 'Scan now',
  onSubmit,
  error,
  disabled,
}: Props) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [value, setValue] = useState(initialValue)
  const [inflight, setInflight] = useState(false)

  useEffect(() => {
    setValue(initialValue)
  }, [initialValue])

  function normalize(raw: string): string {
    const trimmed = raw.trim()
    if (trimmed.startsWith('http')) return trimmed
    if (trimmed.startsWith('github.com/')) return `https://${trimmed}`
    return `https://github.com/${trimmed.replace(/^\/+/, '')}`
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!onSubmit || disabled || inflight) return
    const url = normalize(value)
    setInflight(true)
    try {
      await onSubmit(url)
    } finally {
      setInflight(false)
    }
  }

  return (
    <form className="scan-input" onSubmit={handleSubmit} aria-label="Scan a public GitHub repository">
      <div className="scan-input-row">
        <span className="scan-input-prefix" aria-hidden="true">
          github.com/
        </span>
        <input
          ref={inputRef}
          className="scan-input-field"
          type="text"
          spellCheck={false}
          autoComplete="off"
          placeholder="<org>/<repo>"
          aria-label="Repository path"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          disabled={disabled || inflight}
        />
        <button
          type="submit"
          className="btn btn-hex btn-primary"
          aria-label={submitLabel}
          disabled={disabled || inflight || value.trim() === ''}
        >
          <span className="btn-hex-cap" aria-hidden="true" />
          <span className="btn-label">{inflight ? 'Submitting…' : submitLabel}</span>
        </button>
      </div>
      {error ? (
        <p className="scan-input-error" role="alert">
          {error}
        </p>
      ) : null}
    </form>
  )
}
