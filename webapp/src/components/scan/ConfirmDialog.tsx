import type { RefObject } from 'react'

interface Props {
  /** Native <dialog> ref — caller opens via `ref.current?.showModal()`. */
  dialogRef: RefObject<HTMLDialogElement | null>
  titleId: string
  title: string
  description: string
  /** Generic error copy (no token-validity oracle — P1-6); null hides it. */
  error?: string | null
  /** Disables both buttons + swaps the confirm label while a mutation is in flight. */
  pending: boolean
  confirmLabel: string
  pendingLabel: string
  /** `danger` styles the confirm button as destructive (Delete). */
  confirmVariant?: 'primary' | 'danger'
  onConfirm: () => void
}

/**
 * Focus-trapped confirm dialog for the destructive unlisted actions (promote /
 * delete). Native `<dialog>` gives focus-trap + Esc + focus-restore for free;
 * backdrop click closes (unless in flight). Shared by both manage-bar actions so
 * the destructive-UX hardening (disable-in-flight, explicit labels, generic
 * error) lives in one place — P1-6 / D-UP-26.
 */
export default function ConfirmDialog({
  dialogRef,
  titleId,
  title,
  description,
  error,
  pending,
  confirmLabel,
  pendingLabel,
  confirmVariant = 'primary',
  onConfirm,
}: Props) {
  return (
    // biome-ignore lint/a11y/useKeyWithClickEvents: backdrop dismiss is supplementary to Esc + Cancel; the dialog is keyboard-complete
    <dialog
      ref={dialogRef}
      className="confirm-dialog"
      aria-labelledby={titleId}
      onClick={(e) => {
        if (e.target === dialogRef.current && !pending) dialogRef.current?.close()
      }}
    >
      <h3 id={titleId}>{title}</h3>
      <p>{description}</p>
      {error && <p className="confirm-error">{error}</p>}
      <div className="confirm-actions">
        <button
          type="button"
          className="btn paper sm"
          onClick={() => dialogRef.current?.close()}
          disabled={pending}
        >
          Cancel
        </button>
        <button
          type="button"
          className={`btn ${confirmVariant === 'danger' ? 'danger' : 'primary'} sm`}
          onClick={onConfirm}
          disabled={pending}
        >
          {pending ? pendingLabel : confirmLabel}
        </button>
      </div>
    </dialog>
  )
}
