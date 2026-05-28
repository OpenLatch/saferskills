import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { axe } from 'vitest-axe'
import Kbd from '../../../components/atoms/Kbd'

describe('Kbd', () => {
  it('renders the label inside a <kbd>', () => {
    render(<Kbd>⌘K</Kbd>)
    const el = screen.getByText('⌘K')
    expect(el.tagName.toLowerCase()).toBe('kbd')
    expect(el.classList.contains('kbd-chip')).toBe(true)
  })

  it('forwards className', () => {
    const { container } = render(<Kbd className="extra">⌘J</Kbd>)
    expect(container.querySelector('kbd.kbd-chip.extra')).not.toBeNull()
  })

  it('is accessible (vitest-axe)', async () => {
    const { container } = render(
      <div>
        <Kbd>⌘K</Kbd>
        <Kbd>Ctrl+K</Kbd>
      </div>,
    )
    const results = await axe(container)
    expect(results.violations).toHaveLength(0)
  })
})
