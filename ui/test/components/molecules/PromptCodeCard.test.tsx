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

  it('exposes the scrollable body as a keyboard-focusable, labelled region', () => {
    // Regression: the `.pc-body` overflows (max-height + overflow:auto), so axe's
    // `scrollable-region-focusable` (WCAG 2 A/AA, serious) requires it be reachable
    // by keyboard. jsdom can't compute scroll, so assert the structure directly.
    const { container } = render(
      <PromptCodeCard title="SaferSkills Agent Scan Prompt" lines={LINES} copyState="idle" onCopy={() => {}} />,
    )
    const body = container.querySelector('.pc-body')
    expect(body?.getAttribute('tabindex')).toBe('0')
    expect(body?.getAttribute('role')).toBe('group')
    expect(body?.getAttribute('aria-label')).toBe('SaferSkills Agent Scan Prompt')
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

  // Regression: the v3 prompt body lost its syntax tint when `.code-editor`
  // became this generic block — `tinted` restores it (placeholders, verbs,
  // headers, the bold title, the privacy paragraph).
  describe('tinted', () => {
    const TINTED = [
      'Run a **SaferSkills Agent Scan** on this agent.',
      '1. Fetch the signed test pack: GET {{PACK_URL}}',
      '   with HTTP header  X-SaferSkills-Run-Token: {{RUN_TOKEN}}',
      'Privacy: SaferSkills records company-level signal only.',
    ]

    it('wraps placeholders, verbs, headers, the bold title and privacy line in token spans', () => {
      const { container } = render(
        <PromptCodeCard title="Prompt" lines={TINTED} tinted copyState="idle" onCopy={() => {}} />,
      )
      expect(container.querySelector('.pc-tok-m')?.textContent).toBe('**SaferSkills Agent Scan**')
      expect(container.querySelector('.pc-tok-k')?.textContent).toBe('1.')
      expect([...container.querySelectorAll('.pc-tok-s')].map((e) => e.textContent)).toContain(
        '{{PACK_URL}}',
      )
      expect(container.querySelector('.pc-tok-f')?.textContent).toBe('X-SaferSkills-Run-Token')
      expect(container.querySelector('.pc-tok-c')?.textContent).toBe(TINTED[3])
      // The prompt text is still selectable as plain runs between tokens.
      expect(screen.getByText(/Fetch the signed test pack/)).toBeInTheDocument()
    })

    it('renders plain text (no token spans) when not tinted', () => {
      const { container } = render(
        <PromptCodeCard title="Prompt" lines={TINTED} copyState="idle" onCopy={() => {}} />,
      )
      expect(container.querySelector('[class^="pc-tok-"]')).toBeNull()
    })

    it('has no a11y violations when tinted', async () => {
      const { container } = render(
        <PromptCodeCard title="Prompt" lines={TINTED} tinted copyState="idle" onCopy={() => {}} />,
      )
      const results = await axe(container)
      expect(results.violations).toHaveLength(0)
    })
  })
})
