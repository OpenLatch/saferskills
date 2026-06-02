import type { Story } from '@ladle/react'
import { useRef, useState } from 'react'
import Dialog from '../../components/atoms/Dialog'

function Frame({
  variant,
  withError,
}: {
  variant?: 'primary' | 'danger'
  withError?: boolean
}) {
  const ref = useRef<HTMLDialogElement>(null)
  const [pending, setPending] = useState(false)
  return (
    <div style={{ padding: 40 }}>
      <button type="button" className="btn primary sm" onClick={() => ref.current?.showModal()}>
        Open dialog
      </button>
      <Dialog
        dialogRef={ref}
        titleId="story-dialog"
        title={variant === 'danger' ? 'Delete this report?' : 'Promote to public?'}
        description={
          variant === 'danger'
            ? 'This permanently deletes the report. Anyone with the link will lose access. This cannot be undone.'
            : 'This publishes the report permanently and lists it in the catalog. This cannot be undone.'
        }
        error={withError ? "Couldn't complete that — the link may have expired or been deleted." : null}
        pending={pending}
        confirmLabel={variant === 'danger' ? 'Delete permanently' : 'Publish permanently'}
        pendingLabel={variant === 'danger' ? 'Deleting…' : 'Publishing…'}
        confirmVariant={variant}
        onConfirm={() => {
          setPending(true)
          setTimeout(() => {
            setPending(false)
            ref.current?.close()
          }, 1200)
        }}
      />
    </div>
  )
}

export const Promote: Story = () => <Frame />
export const Delete: Story = () => <Frame variant="danger" />
export const WithError: Story = () => <Frame variant="danger" withError />
