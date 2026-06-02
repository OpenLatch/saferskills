import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'
import SegmentedTabs, { panelId } from '../../../components/atoms/SegmentedTabs'

const TABS = [
  { id: 'upload', label: 'Upload', accent: 'teal' as const },
  { id: 'url', label: 'Scan repo', accent: 'orange' as const },
]

describe('SegmentedTabs', () => {
  it('renders a labelled tablist with one tab per entry', () => {
    render(<SegmentedTabs ariaLabel="Scan mode" tabs={TABS} value="upload" onChange={() => {}} />)
    expect(screen.getByRole('tablist', { name: /scan mode/i })).toBeInTheDocument()
    expect(screen.getAllByRole('tab')).toHaveLength(2)
  })

  it('marks the active tab selected and applies roving tabindex', () => {
    render(<SegmentedTabs ariaLabel="Scan mode" tabs={TABS} value="upload" onChange={() => {}} />)
    const [upload, url] = screen.getAllByRole('tab')
    expect(upload).toHaveAttribute('aria-selected', 'true')
    expect(upload).toHaveAttribute('tabindex', '0')
    expect(url).toHaveAttribute('aria-selected', 'false')
    expect(url).toHaveAttribute('tabindex', '-1')
  })

  it('calls onChange on click', () => {
    const onChange = vi.fn()
    render(<SegmentedTabs ariaLabel="Scan mode" tabs={TABS} value="upload" onChange={onChange} />)
    fireEvent.click(screen.getByRole('tab', { name: 'Scan repo' }))
    expect(onChange).toHaveBeenCalledWith('url')
  })

  it('moves focus with ArrowRight and activates with Enter', () => {
    const onChange = vi.fn()
    render(<SegmentedTabs ariaLabel="Scan mode" tabs={TABS} value="upload" onChange={onChange} />)
    const [upload, url] = screen.getAllByRole('tab')
    upload.focus()
    fireEvent.keyDown(upload, { key: 'ArrowRight' })
    expect(document.activeElement).toBe(url)
    fireEvent.keyDown(url, { key: 'Enter' })
    expect(onChange).toHaveBeenCalledWith('url')
  })

  it('wires aria-controls to the panel id helper', () => {
    render(
      <SegmentedTabs ariaLabel="Scan mode" idBase="t" tabs={TABS} value="upload" onChange={() => {}} />,
    )
    expect(screen.getByRole('tab', { name: 'Upload' })).toHaveAttribute(
      'aria-controls',
      panelId('t', 'upload'),
    )
  })

  it('is accessible (vitest-axe)', async () => {
    const { container } = render(
      <div>
        <SegmentedTabs ariaLabel="Scan mode" idBase="t" tabs={TABS} value="upload" onChange={() => {}} />
        <div id={panelId('t', 'upload')} role="tabpanel" aria-labelledby="t-tab-upload">
          Upload
        </div>
        <div id={panelId('t', 'url')} role="tabpanel" aria-labelledby="t-tab-url" hidden>
          URL
        </div>
      </div>,
    )
    const results = await axe(container)
    expect(results.violations).toHaveLength(0)
  })
})
