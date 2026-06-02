import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'
import Select from '../../../components/atoms/Select'

const OPTIONS = [
  { value: 'most_installed', label: 'Most installed' },
  { value: 'recent', label: 'Recently updated' },
  { value: 'highest_score', label: 'Highest score' },
]

describe('Select', () => {
  it('renders a trigger showing the selected label, no menu until opened', () => {
    render(<Select value="recent" options={OPTIONS} onChange={() => {}} ariaLabel="Sort catalog" />)
    const trigger = screen.getByRole('button', { name: /sort catalog/i })
    expect(trigger).toHaveTextContent('Recently updated')
    expect(trigger).toHaveAttribute('aria-expanded', 'false')
    expect(screen.queryByRole('listbox')).toBeNull()
  })

  it('opens the listbox on click and marks the selected option', () => {
    render(
      <Select value="recent" options={OPTIONS} onChange={() => {}} ariaLabel="Sort catalog" />
    )
    fireEvent.click(screen.getByRole('button', { name: /sort catalog/i }))
    expect(screen.getByRole('listbox')).toBeInTheDocument()
    const selected = screen.getByRole('option', { selected: true })
    expect(selected).toHaveTextContent('Recently updated')
  })

  it('commits a value on option click and closes', () => {
    const onChange = vi.fn()
    render(<Select value="recent" options={OPTIONS} onChange={onChange} ariaLabel="Sort catalog" />)
    fireEvent.click(screen.getByRole('button', { name: /sort catalog/i }))
    fireEvent.click(screen.getByRole('option', { name: 'Highest score' }))
    expect(onChange).toHaveBeenCalledWith('highest_score')
    expect(screen.queryByRole('listbox')).toBeNull()
  })

  it('moves the active descendant with ArrowDown and commits on Enter', () => {
    const onChange = vi.fn()
    render(
      <Select value="most_installed" options={OPTIONS} onChange={onChange} ariaLabel="Sort catalog" />
    )
    fireEvent.click(screen.getByRole('button', { name: /sort catalog/i }))
    const listbox = screen.getByRole('listbox')
    fireEvent.keyDown(listbox, { key: 'ArrowDown' })
    fireEvent.keyDown(listbox, { key: 'Enter' })
    expect(onChange).toHaveBeenCalledWith('recent')
  })

  it('closes on Escape without committing', () => {
    const onChange = vi.fn()
    render(<Select value="recent" options={OPTIONS} onChange={onChange} ariaLabel="Sort catalog" />)
    fireEvent.click(screen.getByRole('button', { name: /sort catalog/i }))
    fireEvent.keyDown(screen.getByRole('listbox'), { key: 'Escape' })
    expect(screen.queryByRole('listbox')).toBeNull()
    expect(onChange).not.toHaveBeenCalled()
  })

  it('is accessible when open (vitest-axe)', async () => {
    const { container } = render(
      <Select value="recent" options={OPTIONS} onChange={() => {}} ariaLabel="Sort catalog" />
    )
    fireEvent.click(screen.getByRole('button', { name: /sort catalog/i }))
    const results = await axe(container)
    expect(results.violations).toHaveLength(0)
  })
})
