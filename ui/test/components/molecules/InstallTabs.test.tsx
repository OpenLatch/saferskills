import { describe, expect, it } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { axe } from 'vitest-axe'
import InstallTabs from '../../../components/molecules/InstallTabs'
import Toast from '../../../components/atoms/Toast'

describe('InstallTabs', () => {
  it('renders 8 agent rows in the sidebar and starts on the first', () => {
    const { container } = render(<InstallTabs scanSlug="github-mcp" />)
    const rows = container.querySelectorAll('.iw-row')
    expect(rows.length).toBe(8)
    expect(rows[0]).toHaveAttribute('aria-pressed', 'true')
  })

  it('renders the four verb tabs and defaults to install', () => {
    render(<InstallTabs scanSlug="github-mcp" />)
    expect(screen.getAllByRole('tab')).toHaveLength(4)
    const installTab = screen.getByRole('tab', { name: /install/i })
    expect(installTab).toHaveAttribute('aria-selected', 'true')
  })

  it('updates the breadcrumb + title-agent label when switching agents', () => {
    const { container } = render(<InstallTabs scanSlug="github-mcp" />)
    const cursorRow = screen.getByRole('button', { name: /Cursor/i })
    fireEvent.click(cursorRow)
    expect(cursorRow).toHaveAttribute('aria-pressed', 'true')
    const crumb = container.querySelector('.iw-bread .crumb.cur')
    expect(crumb?.textContent).toBe('cursor')
    expect(container.querySelector('.iw-title-agent')?.textContent).toBe('Cursor')
  })

  it('rotates the terminal body + chrome when switching verbs', () => {
    const { container } = render(<InstallTabs scanSlug="github-mcp" />)
    const scanTab = screen.getByRole('tab', { name: /scan/i })
    fireEvent.click(scanTab)
    expect(scanTab).toHaveAttribute('aria-selected', 'true')
    // the scan verb renders the local-audit report + retitles the chrome
    expect(container.querySelector('#iw-pane')?.textContent).toContain('local audit')
    expect(container.querySelector('.iw-title-agent')?.textContent).toBe('local audit')
    // and the copy-command target follows the active verb
    expect(screen.getByRole('button', { name: /Copy command/i })).toHaveAttribute(
      'aria-label',
      'Copy command: npx saferskills scan',
    )
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
