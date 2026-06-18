import { useId, useRef, useState } from 'react'
import Dialog from '../atoms/Dialog'

/**
 * Vendor right-of-reply. The capability-token holder attaches a
 * ≤`maxLength`-char public reply via a Dialog with a live character counter.
 * Presentational only — the webapp wires `onSubmit` (POST + telemetry). A report
 * that already carries a reply renders it read-only via `existingReply`.
 */
export default function RightOfReplyForm({
  onSubmit,
  existingReply = null,
  maxLength = 500,
}: {
  onSubmit: (body: string) => Promise<void>
  existingReply?: string | null
  maxLength?: number
}) {
  const dialogRef = useRef<HTMLDialogElement | null>(null)
  const titleId = useId()
  const [body, setBody] = useState('')
  const [pending, setPending] = useState(false)
  const [done, setDone] = useState(false)
  const [error, setError] = useState<string | null>(null)

  if (existingReply) {
    return (
      <div className="ror-existing">
        <span className="ror-label">Vendor reply</span>
        <p>{existingReply}</p>
      </div>
    )
  }

  async function confirm() {
    if (!body.trim()) {
      setError('Write a reply before posting.')
      return
    }
    setPending(true)
    setError(null)
    try {
      await onSubmit(body.trim())
      dialogRef.current?.close()
      setDone(true)
    } catch {
      setError('Could not post your reply just now — please try again.')
    } finally {
      setPending(false)
    }
  }

  return (
    <div className="ror">
      {done ? (
        <span className="ror-done" role="status">
          ✓ Reply submitted
        </span>
      ) : (
        <button
          type="button"
          className="btn paper sm"
          onClick={() => dialogRef.current?.showModal()}
        >
          Add a public reply
        </button>
      )}
      <Dialog
        dialogRef={dialogRef}
        titleId={titleId}
        title="Add a public reply"
        description={
          <span className="ror-field">
            <label htmlFor={`${titleId}-ta`}>Your reply (public, ≤{maxLength} chars)</label>
            <textarea
              id={`${titleId}-ta`}
              value={body}
              maxLength={maxLength}
              rows={5}
              onChange={(e) => setBody(e.target.value)}
              placeholder="Add context or a correction. This appears publicly on the report."
            />
            <span className="ror-count" aria-live="polite">
              {body.length}/{maxLength}
            </span>
          </span>
        }
        error={error}
        pending={pending}
        confirmLabel="Post reply"
        pendingLabel="Posting…"
        onConfirm={confirm}
      />
    </div>
  )
}
