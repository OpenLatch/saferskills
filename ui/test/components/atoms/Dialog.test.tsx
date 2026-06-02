import { fireEvent, render, screen } from '@testing-library/react'
import { useRef } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'
import Dialog from '../../../components/atoms/Dialog'

function Harness(props: {
  pending?: boolean
  error?: string | null
  confirmVariant?: 'primary' | 'danger'
  onConfirm?: () => void
}) {
  const ref = useRef<HTMLDialogElement>(null)
  return (
    <Dialog
      dialogRef={ref}
      titleId="t1"
      title="Delete this report?"
      description="This cannot be undone."
      error={props.error}
      pending={props.pending}
      confirmLabel="Delete permanently"
      pendingLabel="Deleting…"
      confirmVariant={props.confirmVariant}
      onConfirm={props.onConfirm ?? (() => {})}
    />
  )
}

describe('Dialog', () => {
  it('renders title, description, and both action labels', () => {
    render(<Harness />)
    expect(screen.getByText('Delete this report?')).toBeInTheDocument()
    expect(screen.getByText('This cannot be undone.')).toBeInTheDocument()
    expect(screen.getByText('Cancel')).toBeInTheDocument()
    expect(screen.getByText('Delete permanently')).toBeInTheDocument()
  })

  it('wires aria-labelledby to the heading id', () => {
    const { container } = render(<Harness />)
    const dialog = container.querySelector('dialog.confirm-dialog')
    expect(dialog?.getAttribute('aria-labelledby')).toBe('t1')
    expect(container.querySelector('h3#t1')).not.toBeNull()
  })

  it('swaps to the pending label and disables both buttons while pending', () => {
    render(<Harness pending />)
    expect(screen.getByText('Deleting…')).toBeInTheDocument()
    expect(screen.queryByText('Delete permanently')).toBeNull()
    expect((screen.getByText('Cancel') as HTMLButtonElement).disabled).toBe(true)
    expect((screen.getByText('Deleting…') as HTMLButtonElement).disabled).toBe(true)
  })

  it('calls onConfirm when the confirm button is clicked', () => {
    const onConfirm = vi.fn()
    render(<Harness onConfirm={onConfirm} />)
    fireEvent.click(screen.getByText('Delete permanently'))
    expect(onConfirm).toHaveBeenCalledOnce()
  })

  it('renders the generic error when provided', () => {
    const { container } = render(<Harness error="Couldn't complete that." />)
    expect(container.querySelector('.confirm-error')?.textContent).toBe("Couldn't complete that.")
  })

  it('styles the confirm button as danger', () => {
    const { container } = render(<Harness confirmVariant="danger" />)
    expect(container.querySelector('.confirm-actions .btn.danger')).not.toBeNull()
  })

  it('has no critical a11y violations', async () => {
    const { container } = render(<Harness />)
    const results = await axe(container)
    expect(results.violations).toHaveLength(0)
  })
})
