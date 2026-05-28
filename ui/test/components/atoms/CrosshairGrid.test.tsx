import { describe, expect, it, vi } from 'vitest'
import { render } from '@testing-library/react'
import { axe } from 'vitest-axe'
import CrosshairGrid from '../../../components/atoms/CrosshairGrid'

describe('CrosshairGrid', () => {
  it('renders a decorative canvas', () => {
    const { container } = render(<CrosshairGrid />)
    const canvas = container.querySelector('canvas')
    expect(canvas).not.toBeNull()
    expect(canvas?.getAttribute('aria-hidden')).toBe('true')
    expect(canvas?.classList.contains('crosshair-grid')).toBe(true)
  })

  it('removes every window listener it registered on unmount', () => {
    const addSpy = vi.spyOn(window, 'addEventListener')
    const removeSpy = vi.spyOn(window, 'removeEventListener')

    const { unmount } = render(<CrosshairGrid />)

    const tracked = new Set(['pointermove', 'pointerleave', 'touchmove', 'resize'])
    const added = addSpy.mock.calls
      .map((c) => c[0] as string)
      .filter((name) => tracked.has(name))

    unmount()

    const removed = removeSpy.mock.calls
      .map((c) => c[0] as string)
      .filter((name) => tracked.has(name))

    for (const name of added) {
      expect(removed).toContain(name)
    }

    addSpy.mockRestore()
    removeSpy.mockRestore()
  })

  it('is accessible (vitest-axe)', async () => {
    const { container } = render(<CrosshairGrid />)
    const results = await axe(container)
    expect(results.violations).toHaveLength(0)
  })
})
