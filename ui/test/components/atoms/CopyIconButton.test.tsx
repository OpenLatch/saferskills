import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'
import CopyIconButton from '../../../components/atoms/CopyIconButton'

describe('CopyIconButton', () => {
  it('writes the full value to the clipboard and flips to a copied state', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.assign(navigator, { clipboard: { writeText } })

    render(<CopyIconButton value="d81c…full-sha…095c" label="Copy SHA-256" />)
    fireEvent.click(screen.getByRole('button', { name: 'Copy SHA-256' }))
    expect(writeText).toHaveBeenCalledWith('d81c…full-sha…095c')
    // The button re-labels to "Copied" after a successful write.
    await waitFor(() => expect(screen.getByRole('button', { name: 'Copied' })).toBeTruthy())
  })

  it('is accessible (vitest-axe)', async () => {
    const { container } = render(<CopyIconButton value="abc" label="Copy SHA-256" />)
    const results = await axe(container)
    expect(results.violations).toHaveLength(0)
  })
})
