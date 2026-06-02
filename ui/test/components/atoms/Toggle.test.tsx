import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'
import Toggle from '../../../components/atoms/Toggle'

describe('Toggle', () => {
  it('renders a switch reflecting checked state + label', () => {
    render(<Toggle checked onChange={() => {}} label="Make results public" />)
    const sw = screen.getByRole('switch', { name: /make results public/i })
    expect(sw).toHaveAttribute('aria-checked', 'true')
  })

  it('calls onChange with the negated value on click', () => {
    const onChange = vi.fn()
    render(<Toggle checked={false} onChange={onChange} label="Make results public" />)
    fireEvent.click(screen.getByRole('switch'))
    expect(onChange).toHaveBeenCalledWith(true)
  })

  it('applies the orange tone + compact modifiers', () => {
    render(<Toggle checked onChange={() => {}} label="Make results public" tone="orange" compact />)
    const sw = screen.getByRole('switch')
    expect(sw).toHaveAttribute('data-tone', 'orange')
    expect(sw.className).toContain('toggle--compact')
  })

  it('does not fire when disabled', () => {
    const onChange = vi.fn()
    render(<Toggle checked onChange={onChange} label="Make results public" disabled />)
    fireEvent.click(screen.getByRole('switch'))
    expect(onChange).not.toHaveBeenCalled()
  })

  it('is accessible (vitest-axe)', async () => {
    const { container } = render(<Toggle checked onChange={() => {}} label="Make results public" />)
    const results = await axe(container)
    expect(results.violations).toHaveLength(0)
  })
})
