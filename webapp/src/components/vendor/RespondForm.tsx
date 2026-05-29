import Button from '@ui/components/atoms/Button'
import Eyebrow from '@ui/components/atoms/Eyebrow'
import { useState } from 'react'

import { submitVendorResponse } from '@/lib/api/vendor'
import RenderMarkdown from './RenderMarkdown'

interface Props {
  slug: string
  githubOrg: string
  githubRepo: string
}

const MAX_CHARS = 2000

/**
 * The verified-branch response form. The HttpOnly `ss_vendor_session` cookie is
 * forwarded server-side by the `/respond/submit` Astro endpoint — no bearer
 * token in JS. 2000-char Markdown limit + live preview + optional re-scan.
 */
export default function RespondForm({ slug, githubOrg, githubRepo }: Props) {
  const [body, setBody] = useState('')
  const [triggerRescan, setTriggerRescan] = useState(true)
  const [preview, setPreview] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const charCount = body.length
  const overLimit = charCount > MAX_CHARS

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setSubmitting(true)
    setError(null)
    try {
      await submitVendorResponse(slug, { body_markdown: body, trigger_rescan: triggerRescan })
      window.location.assign(`/items/${slug}#vendor-response`)
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Submission failed.'
      setError(message)
      // A 401 means the 15-minute session lapsed during composition.
      if (/session|401|unauthor/i.test(message)) {
        setTimeout(() => window.location.assign(`/items/${slug}/respond`), 1800)
      }
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <form className="respond-form" onSubmit={submit}>
      <div className="verified-banner">
        ✓ Verified control of{' '}
        <code>
          github.com/{githubOrg}/{githubRepo}
        </code>
        . Your response is attributed to the repository, not to a personal handle.
      </div>

      <label className="form-label">
        <Eyebrow>YOUR RESPONSE</Eyebrow>
        <textarea
          className="form-textarea"
          value={body}
          onChange={(e) => setBody(e.currentTarget.value)}
          rows={8}
          placeholder="Markdown supported. Max 2000 characters."
          required
          disabled={submitting}
          aria-required="true"
        />
      </label>

      <div className="form-meta">
        <span
          className={`char-count${charCount > MAX_CHARS * 0.9 ? ' warn' : ''}`}
          aria-live="polite"
        >
          {charCount} / {MAX_CHARS}
        </span>
        <button type="button" className="preview-toggle" onClick={() => setPreview((p) => !p)}>
          {preview ? 'Edit' : 'Preview'}
        </button>
      </div>

      {preview && (
        <div className="form-preview">
          {body.trim() ? (
            <RenderMarkdown body={body} />
          ) : (
            <p className="muted">Nothing to preview yet.</p>
          )}
        </div>
      )}

      <label className="form-checkbox">
        <input
          type="checkbox"
          checked={triggerRescan}
          onChange={(e) => setTriggerRescan(e.currentTarget.checked)}
        />
        Trigger an immediate re-scan after submission
      </label>

      {error && (
        <div className="form-error" role="alert">
          {error}
        </div>
      )}

      <div className="form-actions">
        <Button
          type="submit"
          variant="primary"
          disabled={submitting || charCount === 0 || overLimit}
        >
          {submitting ? 'Submitting…' : 'Submit response →'}
        </Button>
        <a className="form-cancel" href={`/items/${slug}`}>
          Cancel
        </a>
      </div>

      <p className="form-disclaimer">
        Your response appears publicly on the report next to findings. We don't moderate it (except
        spam / illegal content per ToS). You can edit or delete it later via this form.
      </p>
    </form>
  )
}
