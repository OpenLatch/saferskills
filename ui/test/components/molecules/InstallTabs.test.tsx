import { describe, expect, it } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { axe } from 'vitest-axe'
import InstallTabs from '../../../components/molecules/InstallTabs'
import Toast from '../../../components/atoms/Toast'

describe('InstallTabs', () => {
  it('renders 8 agent rows in the sidebar and starts on the first', () => {
    const { container } = render(<InstallTabs scanSlug="github-mcp" />)
    expect(screen.getAllByRole('tab')).toHaveLength(8)
    expect(container.querySelectorAll('.iw-row').length).toBe(8)
    const claudeTab = screen.getByRole('tab', { name: /Claude Code/i })
    expect(claudeTab).toHaveAttribute('aria-selected', 'true')
  })

  it('updates the breadcrumb + title-agent label when switching agents', () => {
    const { container } = render(<InstallTabs scanSlug="github-mcp" />)
    const cursorTab = screen.getByRole('tab', { name: /Cursor/i })
    fireEvent.click(cursorTab)
    expect(cursorTab).toHaveAttribute('aria-selected', 'true')
    const crumb = container.querySelector('.iw-bread .crumb.cur')
    expect(crumb?.textContent).toBe('cursor')
    expect(container.querySelector('.iw-title-agent')?.textContent).toBe('Cursor')
  })

  it('exposes a copy-command button in the chrome', () => {
    render(<InstallTabs scanSlug="github-mcp" />)
    const copyBtn = screen.getByRole('button', { name: /Copy command/i })
    expect(copyBtn.className).toContain('mt-copy')
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
