import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { axe } from 'vitest-axe'
import MultiSelect from '../../../components/molecules/MultiSelect'

const OPTIONS = [
  { value: 'critical', label: 'Critical' },
  { value: 'high', label: 'High' },
  { value: 'info', label: 'Info' },
]

describe('MultiSelect', () => {
  it('opens on click and toggles an option', () => {
    const onChange = vi.fn()
    render(
      <MultiSelect label="Findings" ariaLabel="Findings" options={OPTIONS} selected={[]} onChange={onChange} />
    )
    fireEvent.click(screen.getByRole('button', { name: 'Findings' }))
    expect(screen.getByRole('listbox')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('option', { name: 'High' }))
    expect(onChange).toHaveBeenCalledWith(['high'])
  })

  it('removes a selected option on re-toggle and shows the count badge', () => {
    const onChange = vi.fn()
    render(
      <MultiSelect
        label="Findings"
        ariaLabel="Findings"
        options={OPTIONS}
        selected={['critical']}
        onChange={onChange}
      />
    )
    // Count badge reflects the selection.
    expect(screen.getByText('1')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Findings' }))
    fireEvent.click(screen.getByRole('option', { name: 'Critical' }))
    expect(onChange).toHaveBeenCalledWith([])
  })

  it('has no critical a11y violations (open)', async () => {
    const { container } = render(
      <MultiSelect
        label="Findings"
        ariaLabel="Findings"
        options={OPTIONS}
        selected={['high']}
        onChange={() => {}}
      />
    )
    fireEvent.click(screen.getByRole('button', { name: 'Findings' }))
    const results = await axe(container)
    expect(results.violations).toHaveLength(0)
  })
})
