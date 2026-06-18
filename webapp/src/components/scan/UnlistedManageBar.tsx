import Dialog from '@ui/components/atoms/Dialog'
import Toast, { flashToast } from '@ui/components/atoms/Toast'
import { useId, useRef, useState } from 'react'

import { track } from '@/lib/analytics'
import { deleteUnlisted, promoteUnlisted } from '@/lib/api/scans'

interface Props {
  /** The capability-URL token. Never rendered/logged/echoed. */
  token: string
  /** Current page URL — copied by "Copy link" (carries the token only client-side). */
  shareUrl: string
}

type Pending = null | 'promote' | 'delete'

/**
 * Manage bar for an unlisted scan (mockups 4 + 6): Copy link · Promote · Delete.
 *
 * Possession of the link IS authorization (no auth) — so the same token both
 * views and mutates, surfaced honestly in the inline warning. Destructive
 * actions go through a focus-trapped native `<dialog>` (trap + Esc + focus
 * restore for free), disable while in flight, show explicit destructive labels,
 * and surface a GENERIC error (no invalid/expired/deleted oracle).
 */
export default function UnlistedManageBar({ token, shareUrl }: Props) {
  const promoteRef = useRef<HTMLDialogElement>(null)
  const deleteRef = useRef<HTMLDialogElement>(null)
  const [pending, setPending] = useState<Pending>(null)
  const [error, setError] = useState<string | null>(null)
  const promoteTitle = useId()
  const deleteTitle = useId()

  function copyLink() {
    if (!navigator.clipboard) {
      flashToast('Copy failed — please copy manually')
      return
    }
    navigator.clipboard.writeText(shareUrl).then(
      () => {
        flashToast('Private link copied')
        track('unlisted_manage_action', { action: 'copy_link' })
      },
      () => flashToast('Copy failed — please copy manually')
    )
  }

  function openPromote() {
    setError(null)
    promoteRef.current?.showModal()
  }
  function openDelete() {
    setError(null)
    deleteRef.current?.showModal()
  }

  async function confirmPromote() {
    setPending('promote')
    setError(null)
    try {
      const res = await promoteUnlisted(token)
      track('unlisted_manage_action', { action: 'promote' })
      // Multi-capability-safe: land on the RUN report, never a single /items/<slug>
      // (there is no single slug for an N-capability run).
      window.location.assign(`/scans/${res.run_id}`)
    } catch {
      // Generic — must NOT distinguish invalid / expired / already-deleted.
      setPending(null)
      setError("Couldn't complete that — the link may have expired or been deleted.")
    }
  }

  async function confirmDelete() {
    setPending('delete')
    setError(null)
    try {
      await deleteUnlisted(token)
      track('unlisted_manage_action', { action: 'delete' })
      // Token is purged by navigating away: it is never persisted to
      // sessionStorage / an object URL, and never echoed in the toast.
      deleteRef.current?.close()
      window.location.assign('/scan?deleted=1')
    } catch {
      setPending(null)
      setError("Couldn't complete that — the link may have expired or been deleted.")
    }
  }

  return (
    <>
      {/* biome-ignore lint/a11y/useSemanticElements: a toolbar of actions — role=group is the correct ARIA; a fieldset would impose form chrome */}
      <div className="manage-bar" role="group" aria-label="Manage this unlisted scan">
        <button
          type="button"
          className="mbtn primary"
          onClick={copyLink}
          aria-label="Copy private link"
        >
          ⧉ Copy link
        </button>
        <button
          type="button"
          className="mbtn"
          onClick={openPromote}
          aria-label="Promote this scan to public"
        >
          ↥ Promote to public
        </button>
        <button
          type="button"
          className="mbtn mbtn-danger"
          onClick={openDelete}
          aria-label="Delete this scan"
        >
          <svg
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
            aria-hidden="true"
          >
            <path d="M4 7h16"></path>
            <path d="M9 7V5h6v2"></path>
            <path d="M6.5 7l1 13h9l1-13"></path>
          </svg>
          Delete
        </button>
      </div>
      <p className="manage-warn">Anyone with this link can also delete or publish it.</p>

      <Dialog
        dialogRef={promoteRef}
        titleId={promoteTitle}
        title="Promote to public?"
        description="This publishes the report permanently and lists it in the catalog. This cannot be undone."
        error={error}
        pending={pending === 'promote'}
        confirmLabel="Publish permanently"
        pendingLabel="Publishing…"
        onConfirm={confirmPromote}
      />

      <Dialog
        dialogRef={deleteRef}
        titleId={deleteTitle}
        title="Delete this report?"
        description="This permanently deletes the report. Anyone with the link will lose access. This cannot be undone."
        error={error}
        pending={pending === 'delete'}
        confirmLabel="Delete permanently"
        pendingLabel="Deleting…"
        confirmVariant="danger"
        onConfirm={confirmDelete}
      />

      <Toast />
    </>
  )
}
