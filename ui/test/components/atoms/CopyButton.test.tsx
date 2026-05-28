import { describe, expect, it, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { axe } from 'vitest-axe'
import CopyButton from '../../../components/atoms/CopyButton'
import Toast from '../../../components/atoms/Toast'

describe('CopyButton', () => {
  it('copies the value to the clipboard on click', () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.assign(navigator, { clipboard: { writeText } })

    render(
      <>
        <CopyButton value="npx saferskills install github-mcp" />
        <Toast />
      </>,
    )
    fireEvent.click(screen.getByRole('button', { name: /copy/i }))
    expect(writeText).toHaveBeenCalledWith('npx saferskills install github-mcp')
  })

  it('is accessible (vitest-axe)', async () => {
    const { container } = render(
      <>
        <CopyButton value="abc" />
        <Toast />
      </>,
    )
    const results = await axe(container)
    expect(results.violations).toHaveLength(0)
  })
})
