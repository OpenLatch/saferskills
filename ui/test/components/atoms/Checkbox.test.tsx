import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'
import Checkbox from '../../../components/atoms/Checkbox'

describe('Checkbox', () => {
  it('renders a checkbox reflecting checked state + label', () => {
    render(<Checkbox checked onChange={() => {}} label="Trigger a re-scan" />)
    const cb = screen.getByRole('checkbox', { name: /trigger a re-scan/i })
    expect(cb).toHaveAttribute('aria-checked', 'true')
  })

  it('calls onChange with the negated value on click', () => {
    const onChange = vi.fn()
    render(<Checkbox checked={false} onChange={onChange} label="Skill" />)
    fireEvent.click(screen.getByRole('checkbox', { name: 'Skill' }))
    expect(onChange).toHaveBeenCalledWith(true)
  })

  it('renders a trailing count', () => {
    render(<Checkbox checked onChange={() => {}} label="Skill" count={1234} />)
    expect(screen.getByText('1,234')).toBeInTheDocument()
  })

  it('applies the radio + block modifiers', () => {
    render(<Checkbox variant="radio" block checked onChange={() => {}} label="All sources" />)
    const cb = screen.getByRole('checkbox', { name: 'All sources' })
    expect(cb.className).toContain('ds-check--radio')
    expect(cb.className).toContain('ds-check--block')
  })

  it('renders the adornment node', () => {
    render(
      <Checkbox
        checked
        onChange={() => {}}
        label="Green"
        adornment={<span data-testid="dot" />}
      />
    )
    expect(screen.getByTestId('dot')).toBeInTheDocument()
  })

  it('is accessible (vitest-axe)', async () => {
    const { container } = render(
      <Checkbox checked onChange={() => {}} label="Trigger a re-scan" />
    )
    const results = await axe(container)
    expect(results.violations).toHaveLength(0)
  })
})
