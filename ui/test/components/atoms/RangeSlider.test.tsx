import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'
import RangeSlider from '../../../components/atoms/RangeSlider'

describe('RangeSlider', () => {
  it('renders both thumbs and the value caption', () => {
    render(<RangeSlider min={40} max={90} onChange={() => {}} />)
    expect(screen.getByLabelText('Minimum')).toHaveValue('40')
    expect(screen.getByLabelText('Maximum')).toHaveValue('90')
    expect(screen.getByText('40')).toBeInTheDocument()
    expect(screen.getByText('90')).toBeInTheDocument()
  })

  it('clamps the lower thumb below the upper (no cross)', () => {
    const onChange = vi.fn()
    render(<RangeSlider min={40} max={50} onChange={onChange} />)
    // Try to drag min up to 80 — must clamp to max-1 = 49.
    fireEvent.change(screen.getByLabelText('Minimum'), { target: { value: '80' } })
    expect(onChange).toHaveBeenCalledWith(49, 50)
  })

  it('clamps the upper thumb above the lower (no cross)', () => {
    const onChange = vi.fn()
    render(<RangeSlider min={40} max={50} onChange={onChange} />)
    fireEvent.change(screen.getByLabelText('Maximum'), { target: { value: '10' } })
    expect(onChange).toHaveBeenCalledWith(40, 41)
  })

  it('honors custom aria + cap labels', () => {
    render(
      <RangeSlider
        min={2}
        max={8}
        onChange={() => {}}
        minAriaLabel="Minimum score"
        maxAriaLabel="Maximum score"
        minCapLabel="low"
        maxCapLabel="high"
      />,
    )
    expect(screen.getByLabelText('Minimum score')).toBeInTheDocument()
    expect(screen.getByText('low')).toBeInTheDocument()
    expect(screen.getByText('high')).toBeInTheDocument()
  })

  it('has no critical a11y violations', async () => {
    const { container } = render(
      <RangeSlider min={40} max={90} onChange={() => {}} minAriaLabel="Minimum score" maxAriaLabel="Maximum score" />,
    )
    const results = await axe(container)
    expect(results.violations).toHaveLength(0)
  })
})
