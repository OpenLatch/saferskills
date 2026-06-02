import { fireEvent, render, screen, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import FileTabStrip from '@/components/scan/FileTabStrip'
import UploadReport from '@/components/scan/UploadReport'
import { makeMultiFileUploadRun, makeUploadRun } from '../factories/run-report'

vi.mock('@/lib/analytics', () => ({ track: vi.fn() }))

function fileTablist() {
  return screen.getByRole('tablist', { name: 'Scanned files' })
}

describe('UploadReport', () => {
  it('renders one file tab per capability for a multi-file upload', () => {
    const { container } = render(<UploadReport run={makeMultiFileUploadRun()} ruleCount={55} />)
    const tabs = within(fileTablist()).getAllByRole('tab')
    expect(tabs).toHaveLength(3)
    expect(tabs[0].textContent).toContain('prompt')
    expect(tabs[1].textContent).toContain('install')
    expect(tabs[2].textContent).toContain('server')
    // First tab active by default; the score box shows the active file's score.
    expect(tabs[0].getAttribute('aria-selected')).toBe('true')
    expect(container.querySelector('.sb-big')?.textContent).toContain('91')
  })

  it('switches the per-file body when another file tab is selected', () => {
    const { container } = render(<UploadReport run={makeMultiFileUploadRun()} ruleCount={55} />)
    // The active score box reads 91 (prompt) initially.
    expect(container.querySelector('.sb-big')?.textContent).toContain('91')
    fireEvent.click(within(fileTablist()).getAllByRole('tab')[1]) // install (52)
    expect(container.querySelector('.sb-big')?.textContent).toContain('52')
    expect(within(fileTablist()).getAllByRole('tab')[1].getAttribute('aria-selected')).toBe('true')
  })

  it('shows each file’s own SHA-256 and swaps it on tab switch', () => {
    const { container } = render(<UploadReport run={makeMultiFileUploadRun()} ruleCount={55} />)
    const provSha = () => container.querySelector('.sk-installbox--meta .sha-cell')?.textContent
    expect(provSha()).toContain('1111…9999') // prompt.md hash
    fireEvent.click(within(fileTablist()).getAllByRole('tab')[1]) // install.sh
    expect(provSha()).toContain('aaaa…beef')
  })

  it('copies the full active SHA-256 via the discreet icon button', () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.assign(navigator, { clipboard: { writeText } })
    render(<UploadReport run={makeMultiFileUploadRun()} ruleCount={55} />)
    // Provenance + Artifact each render a copy icon; both copy the FULL hash.
    fireEvent.click(screen.getAllByRole('button', { name: 'Copy SHA-256' })[0])
    expect(writeText).toHaveBeenCalledWith(
      '1111aaaa2222bbbb3333cccc4444dddd5555eeee6666ffff7777000088889999'
    )
  })

  it('renders NO file-tab strip for a single-file upload (regression gate)', () => {
    render(<UploadReport run={makeUploadRun()} ruleCount={55} />)
    expect(screen.queryByRole('tablist', { name: 'Scanned files' })).toBeNull()
    // The rich single-file body still renders (score box + provenance).
    expect(screen.getByText('Provenance')).toBeTruthy()
  })

  it('is accessible (vitest-axe) for a multi-file upload', async () => {
    const { container } = render(<UploadReport run={makeMultiFileUploadRun()} ruleCount={55} />)
    const results = await axe(container)
    expect(results.violations).toHaveLength(0)
  })
})

describe('FileTabStrip', () => {
  const caps = makeMultiFileUploadRun().capabilities

  it('moves selection with arrow keys (roving tabindex, auto-activation)', () => {
    const onSelect = vi.fn()
    render(
      <FileTabStrip
        caps={caps}
        active={0}
        onSelect={onSelect}
        panelId="mf-panel"
        tabIdBase="mf-tab"
      />
    )
    const tabs = within(fileTablist()).getAllByRole('tab')
    expect(tabs[0].tabIndex).toBe(0)
    expect(tabs[1].tabIndex).toBe(-1)
    fireEvent.keyDown(tabs[0], { key: 'ArrowRight' })
    expect(onSelect).toHaveBeenCalledWith(1)
    fireEvent.keyDown(tabs[0], { key: 'Home' })
    expect(onSelect).toHaveBeenCalledWith(0)
    fireEvent.keyDown(tabs[0], { key: 'End' })
    expect(onSelect).toHaveBeenCalledWith(2)
  })

  it('wraps with ArrowLeft from the first tab to the last', () => {
    const onSelect = vi.fn()
    render(
      <FileTabStrip
        caps={caps}
        active={0}
        onSelect={onSelect}
        panelId="mf-panel"
        tabIdBase="mf-tab"
      />
    )
    fireEvent.keyDown(within(fileTablist()).getAllByRole('tab')[0], { key: 'ArrowLeft' })
    expect(onSelect).toHaveBeenCalledWith(2)
  })

  it('is accessible (vitest-axe)', async () => {
    const { container } = render(
      <>
        <FileTabStrip
          caps={caps}
          active={1}
          onSelect={vi.fn()}
          panelId="mf-panel"
          tabIdBase="mf-tab"
        />
        {/* the tabpanel each tab's aria-controls points at */}
        <div id="mf-panel" role="tabpanel" aria-labelledby="mf-tab-1" />
      </>
    )
    const results = await axe(container)
    expect(results.violations).toHaveLength(0)
  })
})
