import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { axe } from 'vitest-axe'
import RuntimeMonogram, { asRuntimeId, runtimeLabel } from '../../../components/atoms/RuntimeMonogram'

describe('RuntimeMonogram', () => {
  it('renders the runtime name (sr-only by default, visible with showName)', () => {
    const { rerender } = render(<RuntimeMonogram runtime="claude-code" />)
    expect(screen.getByText('Claude Code')).toBeInTheDocument()
    rerender(<RuntimeMonogram runtime="cursor" showName />)
    expect(screen.getByText('Cursor')).toBeInTheDocument()
  })

  it('renders the agent brand logo for a known runtime, monogram for other', () => {
    const { container, rerender } = render(<RuntimeMonogram runtime="claude-code" />)
    // Known agent → an inline SVG brand mark inside the hairline box (no 2-letter text).
    expect(container.querySelector('.rt-mark--logo svg')).not.toBeNull()
    rerender(<RuntimeMonogram runtime="totally-unknown" />)
    // Unknown → the `··` monogram fallback, no logo box.
    expect(container.querySelector('.rt-mark--logo')).toBeNull()
    expect(container.querySelector('.rt-mark')?.textContent).toBe('··')
  })

  it('falls back to Other for an unknown runtime', () => {
    expect(asRuntimeId('totally-unknown')).toBe('other')
    expect(runtimeLabel('totally-unknown')).toBe('Other')
    render(<RuntimeMonogram runtime="totally-unknown" />)
    expect(screen.getByText('Other')).toBeInTheDocument()
  })

  it('has no critical a11y violations', async () => {
    const { container } = render(<RuntimeMonogram runtime="codex" showName />)
    const results = await axe(container)
    expect(results.violations).toHaveLength(0)
  })
})
