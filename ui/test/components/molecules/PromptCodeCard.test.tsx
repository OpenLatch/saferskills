import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { axe } from 'vitest-axe'
import PromptCodeCard from '../../../components/molecules/PromptCodeCard'

const LINES = [
  'Run a **SaferSkills Agent Scan** on this agent.',
  '',
  '1. Fetch the signed test pack: GET {{PACK_URL}}',
]

describe('PromptCodeCard', () => {
  it('renders the title, every line, and an aria-hidden line-number gutter', () => {
    const { container } = render(
      <PromptCodeCard title="SaferSkills Agent Scan Prompt" lines={LINES} copyState="idle" onCopy={() => {}} />,
    )
    expect(screen.getByText('SaferSkills Agent Scan Prompt')).toBeInTheDocument()
    expect(screen.getByText(/Fetch the signed test pack/)).toBeInTheDocument()
    const rows = container.querySelectorAll('.pc-line')
    expect(rows).toHaveLength(3)
    const gutters = container.querySelectorAll('.pc-ln')
    expect(gutters).toHaveLength(3)
    for (const g of gutters) expect(g.getAttribute('aria-hidden')).toBe('true')
    expect(gutters[2]?.textContent).toBe('3')
  })

  it('fires onCopy when the Copy button is clicked', () => {
    const onCopy = vi.fn()
    render(<PromptCodeCard title="Prompt" lines={LINES} copyState="idle" onCopy={onCopy} />)
    fireEvent.click(screen.getByRole('button', { name: 'Copy' }))
    expect(onCopy).toHaveBeenCalledTimes(1)
  })

  it('busy disables the control, shows the pending label, and swallows clicks', () => {
    const onCopy = vi.fn()
    render(<PromptCodeCard title="Prompt" lines={LINES} copyState="busy" onCopy={onCopy} />)
    const btn = screen.getByRole('button', { name: 'Copying…' })
    expect(btn).toBeDisabled()
    fireEvent.click(btn)
    expect(onCopy).not.toHaveBeenCalled()
  })

  it('copied state flips the label and announces it via the live region', () => {
    const { container } = render(
      <PromptCodeCard title="Prompt" lines={LINES} copyState="copied" onCopy={() => {}} />,
    )
    expect(screen.getByRole('button', { name: 'Copied' })).toBeInTheDocument()
    const live = container.querySelector('[role="status"]')
    expect(live?.getAttribute('aria-live')).toBe('polite')
    expect(live?.textContent).toBe('Prompt copied to clipboard')
  })

  it('renders the optional footSlot', () => {
    render(
      <PromptCodeCard
        title="Prompt"
        lines={LINES}
        copyState="idle"
        onCopy={() => {}}
        footSlot={<span>Report will be public</span>}
      />,
    )
    expect(screen.getByText('Report will be public')).toBeInTheDocument()
  })

  it('has no a11y violations (vitest-axe)', async () => {
    const { container } = render(
      <PromptCodeCard
        title="SaferSkills Agent Scan Prompt"
        lines={LINES}
        copyState="idle"
        onCopy={() => {}}
        footSlot={<span>Report will be public</span>}
      />,
    )
    const results = await axe(container)
    expect(results.violations).toHaveLength(0)
  })
})
