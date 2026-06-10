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
