import { useId, useRef, useState } from 'react'
import Dialog from '../atoms/Dialog'

/**
 * The verify-tier waitlist tile shown on EVERY agent report (I-5.6 D-5.6-08). A
 * tile → a Dialog with an account-free, email-optional field → records demand via
 * `onSubmit`. Presentational only: the webapp wires `onSubmit` (POST + telemetry).
 * The independently-observed verification tier itself is out of scope — this tile
 * is the demand signal.
 */
export default function VerifyWaitlistTile({
  onSubmit,
  cta = 'Request independent verification',
}: {
  onSubmit: (email: string | null) => Promise<void>
  cta?: string
}) {
  const dialogRef = useRef<HTMLDialogElement | null>(null)
  const titleId = useId()
  const [email, setEmail] = useState('')
  const [pending, setPending] = useState(false)
  const [done, setDone] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function confirm() {
    setPending(true)
    setError(null)
    try {
      await onSubmit(email.trim() || null)
      dialogRef.current?.close()
      setDone(true)
    } catch {
      setError('Could not record your request just now — please try again.')
    } finally {
      setPending(false)
    }
  }

  return (
    <div className="vw-tile">
      <div className="vw-txt">
        <h3>Want a second opinion?</h3>
        <p>
          Independent verification re-runs this pack on neutral infrastructure. Register interest —
          no account needed.
        </p>
      </div>
      {done ? (
        <span className="vw-done" role="status">
          ✓ Request recorded
        </span>
      ) : (
        <button type="button" className="btn dark sm" onClick={() => dialogRef.current?.showModal()}>
          {cta}
        </button>
      )}
      <Dialog
        dialogRef={dialogRef}
        titleId={titleId}
        title={cta}
        description={
          <label className="vw-field">
            Email <span className="vw-opt">(optional — for a reply)</span>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@example.com"
              autoComplete="email"
            />
          </label>
        }
        error={error}
        pending={pending}
        confirmLabel="Register interest"
        pendingLabel="Recording…"
        onConfirm={confirm}
      />
    </div>
  )
}
