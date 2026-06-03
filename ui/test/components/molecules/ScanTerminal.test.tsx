import { render } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { axe } from 'vitest-axe'
import ScanTerminal, { type TerminalLine } from '../../../components/molecules/ScanTerminal'

const LINES: TerminalLine[] = [
  { id: 'cmd', kind: 'cmd', segments: [{ text: 'saferskills scan ', tone: 'cmd' }, { text: 'github.com/acme/x' }] },
  {
    id: 'r1',
    kind: 'run',
    segments: [{ text: 'SS-SKILL-INJECT-01', tone: 'rule' }, { text: '  ' }, { text: 'SKILL.md', tone: 'path' }],
  },
  { id: 'done', kind: 'done', segments: [{ text: 'scan complete' }] },
]

describe('ScanTerminal', () => {
  it('renders each line + the caret on the last while running', () => {
    const { container, getByText } = render(<ScanTerminal lines={LINES} currentStage="security" />)
    expect(container.querySelectorAll('.scan-term-line')).toHaveLength(3)
    expect(getByText('SS-SKILL-INJECT-01')).toBeTruthy()
    expect(container.querySelector('.scan-term-caret')).not.toBeNull()
  })

  it('drops the caret + live dot when complete', () => {
    const { container } = render(<ScanTerminal lines={LINES} complete />)
    expect(container.querySelector('.scan-term-caret')).toBeNull()
    expect(container.querySelector('.scan-terminal-live-dot')).toBeNull()
  })

  it('is accessible (vitest-axe)', async () => {
    const { container } = render(<ScanTerminal lines={LINES} currentStage="security" />)
    const results = await axe(container)
    expect(results.violations).toHaveLength(0)
  })
})
