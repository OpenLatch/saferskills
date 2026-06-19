import Dialog from '@ui/components/atoms/Dialog'
import Toast, { flashToast } from '@ui/components/atoms/Toast'
import { useId, useRef, useState } from 'react'

import { downloadReportMarkdown } from '@/lib/agent-report-markdown'
import { track } from '@/lib/analytics'
import type { AgentScanReportDetail } from '@/lib/api/agent-scan-types'
import { deleteAgentUnlisted, promoteAgentUnlisted } from '@/lib/api/agent-scans'

interface Props {
  run: AgentScanReportDetail
  shareUrl: string
  /** Token route → adds Promote/Delete; public → share + export only. */
  unlisted?: boolean
  token?: string
}

/**
 * The page-head manage bar (mockup `.manage-bar`/`.mbtn` row, top-right of the
 * Agent Report head). Public: copy-share + Markdown export.
 * Unlisted: adds Promote-to-public + Delete with confirm dialogs.
 * Mounted inside the `.sr-head-r` cell of `agents/[id].astro` + `r/[token].astro`.
 */
export default function AgentReportActions({ run, shareUrl, unlisted = false, token }: Props) {
  const promoteRef = useRef<HTMLDialogElement | null>(null)
  const deleteRef = useRef<HTMLDialogElement | null>(null)
  const promoteTitle = useId()
  const deleteTitle = useId()
  const [busy, setBusy] = useState(false)
  const [manageError, setManageError] = useState<string | null>(null)

  async function onShare() {
    try {
      await navigator.clipboard.writeText(shareUrl)
      flashToast(unlisted ? 'Private link copied' : 'Report link copied')
    } catch {
      flashToast('Copy failed — select the URL manually')
    }
    track('agent_report_shared', {})
  }

  function onExport() {
    downloadReportMarkdown(run)
    track('agent_report_exported', {})
  }

  async function confirmPromote() {
    if (!token) return
    setBusy(true)
    setManageError(null)
    try {
      const { id } = await promoteAgentUnlisted(token)
      window.location.assign(`/agents/${id}`)
    } catch {
      setManageError('Could not promote this report — please try again.')
      setBusy(false)
    }
  }

  async function confirmDelete() {
    if (!token) return
    setBusy(true)
    setManageError(null)
    try {
      await deleteAgentUnlisted(token)
      window.location.assign('/agents')
    } catch {
      setManageError('Could not delete this report — please try again.')
      setBusy(false)
    }
  }

  return (
    <div className="manage-bar">
      <button type="button" className="mbtn primary" onClick={onShare}>
        ⧉ {unlisted ? 'Copy private link' : 'Copy Report Link'}
      </button>
      <button type="button" className="mbtn" onClick={onExport}>
        ↧ Export Markdown
      </button>
      {unlisted && (
        <>
          <button type="button" className="mbtn" onClick={() => promoteRef.current?.showModal()}>
            ↥ Promote to public
          </button>
          <button
            type="button"
            className="mbtn mbtn-danger"
            onClick={() => deleteRef.current?.showModal()}
          >
            Delete
          </button>
          <Dialog
            dialogRef={promoteRef}
            titleId={promoteTitle}
            title="Promote to public?"
            description="This makes the report public and permanent, and removes the 90-day expiry. It cannot be undone."
            error={manageError}
            pending={busy}
            confirmLabel="Promote to public"
            pendingLabel="Promoting…"
            onConfirm={confirmPromote}
          />
          <Dialog
            dialogRef={deleteRef}
            titleId={deleteTitle}
            title="Delete this report?"
            description="Anyone with the link loses access immediately. This cannot be undone."
            error={manageError}
            pending={busy}
            confirmLabel="Delete permanently"
            pendingLabel="Deleting…"
            confirmVariant="danger"
            onConfirm={confirmDelete}
          />
        </>
      )}
      <Toast />
    </div>
  )
}
