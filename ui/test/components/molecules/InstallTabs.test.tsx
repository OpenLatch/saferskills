import { describe, expect, it } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { axe } from 'vitest-axe'
import InstallTabs from '../../../components/molecules/InstallTabs'
import Toast from '../../../components/atoms/Toast'

describe('InstallTabs', () => {
  it('renders 8 default agent tabs and starts on the first', () => {
    render(<InstallTabs scanSlug="github-mcp" />)
    expect(screen.getAllByRole('tab')).toHaveLength(8)
    const claudeTab = screen.getByRole('tab', { name: /Claude Code/i })
    expect(claudeTab).toHaveAttribute('aria-selected', 'true')
  })

  it('switches the active panel when a different tab is clicked', () => {
    render(<InstallTabs scanSlug="github-mcp" />)
    const cursorTab = screen.getByRole('tab', { name: /Cursor/i })
    fireEvent.click(cursorTab)
    expect(cursorTab).toHaveAttribute('aria-selected', 'true')
  })

  it('is accessible (vitest-axe)', async () => {
    const { container } = render(
      <>
        <InstallTabs scanSlug="github-mcp" />
        <Toast />
      </>,
    )
    const results = await axe(container)
    expect(results.violations).toHaveLength(0)
  })
})
