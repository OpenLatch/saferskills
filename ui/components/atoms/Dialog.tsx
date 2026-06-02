import type { ReactNode, RefObject } from 'react'

interface Props {
  /** Native `<dialog>` ref — the caller opens it via `ref.current?.showModal()`. */
  dialogRef: RefObject<HTMLDialogElement | null>
  /** Id of the heading; wired to `aria-labelledby`. */
  titleId: string
  title: string
  description: ReactNode
  /** Generic error copy (e.g. no token-validity oracle); `null`/absent hides it. */
  error?: string | null
  /** Disables both buttons + swaps the confirm label while a mutation is in flight. */
  pending?: boolean
  confirmLabel: string
  /** Confirm label shown while `pending` (falls back to `confirmLabel`). */
  pendingLabel?: string
  /** Cancel button label. */
  cancelLabel?: string
  /** `danger` styles the confirm button as destructive. */
  confirmVariant?: 'primary' | 'danger'
  onConfirm: () => void
  /** Optional explicit cancel handler; defaults to closing the dialog. */
  onCancel?: () => void
}

/**
 * DS modal dialog built on the native `<dialog>` element — focus-trap, Escape,
 * and focus-restore come for free from the platform. Backdrop click dismisses
 * UNLESS a mutation is in flight (`pending`). Two action buttons (cancel +
 * confirm) using the DS `Button` class vocabulary.
 *
 * Generalized from the former webapp `ConfirmDialog`; CSS (`.confirm-dialog*`)
 * is DS-owned in `ui/styles/components.css`.
 */
export default function Dialog({
  dialogRef,
  titleId,
  title,
  description,
  error,
  pending = false,
  confirmLabel,
  pendingLabel,
  cancelLabel = 'Cancel',
  confirmVariant = 'primary',
  onConfirm,
  onCancel,
}: Props) {
  function cancel() {
    if (onCancel) onCancel()
    else dialogRef.current?.close()
  }

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
        <button type="button" className="btn paper sm" onClick={cancel} disabled={pending}>
          {cancelLabel}
        </button>
        <button
          type="button"
          className={`btn ${confirmVariant === 'danger' ? 'danger' : 'primary'} sm`}
          onClick={onConfirm}
          disabled={pending}
        >
          {pending ? (pendingLabel ?? confirmLabel) : confirmLabel}
        </button>
      </div>
    </dialog>
  )
}
