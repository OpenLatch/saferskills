import { beforeAll, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { axe } from 'vitest-axe'
import RightOfReplyForm from '../../../components/molecules/RightOfReplyForm'

beforeAll(() => {
  HTMLDialogElement.prototype.showModal = vi.fn()
  HTMLDialogElement.prototype.close = vi.fn()
})

describe('RightOfReplyForm', () => {
  it('renders an existing reply read-only (no form)', () => {
    render(<RightOfReplyForm onSubmit={async () => {}} existingReply="We fixed it in v2.3." />)
    expect(screen.getByText('Vendor reply')).toBeInTheDocument()
    expect(screen.getByText('We fixed it in v2.3.')).toBeInTheDocument()
    expect(screen.queryByText('Add a public reply')).toBeNull()
  })

  it('submits a reply body and shows the submitted state', async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined)
    const { container } = render(<RightOfReplyForm onSubmit={onSubmit} />)
    const ta = container.querySelector('textarea') as HTMLTextAreaElement
    fireEvent.change(ta, { target: { value: 'Context: this is mitigated.' } })
    fireEvent.click(screen.getByText('Post reply'))
    await waitFor(() => expect(onSubmit).toHaveBeenCalledWith('Context: this is mitigated.'))
    expect(await screen.findByText('✓ Reply submitted')).toBeInTheDocument()
  })

  it('blocks an empty reply', async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined)
    render(<RightOfReplyForm onSubmit={onSubmit} />)
    fireEvent.click(screen.getByText('Post reply'))
    await waitFor(() =>
      expect(screen.getByText('Write a reply before posting.')).toBeInTheDocument(),
    )
    expect(onSubmit).not.toHaveBeenCalled()
  })

  it('has no critical a11y violations', async () => {
    const { container } = render(<RightOfReplyForm onSubmit={async () => {}} />)
    const results = await axe(container)
    expect(results.violations).toHaveLength(0)
  })
})
