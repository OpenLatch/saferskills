import { beforeAll, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { axe } from 'vitest-axe'
import VerifyWaitlistTile from '../../../components/molecules/VerifyWaitlistTile'

beforeAll(() => {
  // jsdom ships no <dialog> modal methods.
  HTMLDialogElement.prototype.showModal = vi.fn()
  HTMLDialogElement.prototype.close = vi.fn()
})

describe('VerifyWaitlistTile', () => {
  it('renders the tile + CTA', () => {
    render(<VerifyWaitlistTile onSubmit={async () => {}} />)
    expect(screen.getByText('Want a second opinion?')).toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: 'Request independent verification' }),
    ).toBeInTheDocument()
  })

  it('submits the email and shows the recorded state', async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined)
    const { container } = render(<VerifyWaitlistTile onSubmit={onSubmit} />)
    const input = container.querySelector('input[type="email"]') as HTMLInputElement
    fireEvent.change(input, { target: { value: 'a@b.com' } })
    fireEvent.click(screen.getByText('Register interest'))
    await waitFor(() => expect(onSubmit).toHaveBeenCalledWith('a@b.com'))
    expect(await screen.findByText('✓ Request recorded')).toBeInTheDocument()
  })

  it('passes null when the email is left blank', async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined)
    render(<VerifyWaitlistTile onSubmit={onSubmit} />)
    fireEvent.click(screen.getByText('Register interest'))
    await waitFor(() => expect(onSubmit).toHaveBeenCalledWith(null))
  })

  it('has no critical a11y violations', async () => {
    const { container } = render(<VerifyWaitlistTile onSubmit={async () => {}} />)
    const results = await axe(container)
    expect(results.violations).toHaveLength(0)
  })
})
