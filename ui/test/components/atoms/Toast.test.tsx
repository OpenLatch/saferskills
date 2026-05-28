import { describe, expect, it } from 'vitest'
import { render, act, waitFor } from '@testing-library/react'
import { axe } from 'vitest-axe'
import Toast, { flashToast } from '../../../components/atoms/Toast'

describe('Toast', () => {
  it('starts hidden, shows on flashToast, hides after duration', async () => {
    const { container } = render(<Toast />)
    const toast = container.querySelector('.toast') as HTMLElement
    expect(toast.classList.contains('show')).toBe(false)

    act(() => { flashToast('Copied', 80) })
    expect(toast.classList.contains('show')).toBe(true)
    expect(toast.textContent).toBe('Copied')

    await waitFor(
      () => expect(toast.classList.contains('show')).toBe(false),
      { timeout: 300 },
    )
  })

  it('is accessible (vitest-axe)', async () => {
    const { container } = render(<Toast />)
    const results = await axe(container)
    expect(results.violations).toHaveLength(0)
  })
})
