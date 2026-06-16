import { act, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

// The island renders ONLY the underline tab control; the panels are SSR'd by
// methodology.astro. So we mount panel fixtures in the document and assert the
// island toggles them — the mirror of ScanModeShell.test.tsx's mountAside().
vi.mock('@/lib/analytics', () => ({ track: vi.fn() }))

import MethodologyTabs from '@/components/methodology/MethodologyTabs'
import { track } from '@/lib/analytics'

/** SSR'd panel fixtures (live OUTSIDE the island, like the real page). */
function mountPanels(initial: 'capability' | 'agent') {
  const root = document.createElement('div')
  root.id = 'methodology-tabs'
  for (const t of ['capability', 'agent'] as const) {
    const panel = document.createElement('div')
    panel.className = 'method-panel'
    panel.dataset.tab = t
    panel.setAttribute('role', 'tabpanel')
    panel.hidden = t !== initial
    if (t === 'capability') {
      // Mimic the FormulaPanel reveal target.
      const reveal = document.createElement('div')
      reveal.setAttribute('data-reveal', '')
      panel.appendChild(reveal)
    }
    root.appendChild(panel)
  }
  document.body.appendChild(root)
  return root
}

function panel(tab: 'capability' | 'agent'): HTMLElement {
  const el = document.querySelector<HTMLElement>(`.method-panel[data-tab="${tab}"]`)
  if (!el) throw new Error(`panel ${tab} missing`)
  return el
}

describe('MethodologyTabs', () => {
  let replaceState: ReturnType<typeof vi.spyOn>

  beforeEach(() => {
    vi.clearAllMocks()
    window.history.replaceState(null, '', '/methodology')
    replaceState = vi.spyOn(history, 'replaceState')
  })

  afterEach(() => {
    replaceState.mockRestore()
    document.body.replaceChildren()
    window.history.replaceState(null, '', '/methodology')
  })

  it('selects Capability rules by default (no replaceState on mount)', () => {
    mountPanels('capability')
    render(<MethodologyTabs />)
    expect(
      screen.getByRole('tab', { name: 'Capability rules' }).getAttribute('aria-selected')
    ).toBe('true')
    expect(panel('capability').hidden).toBe(false)
    expect(panel('agent').hidden).toBe(true)
    expect(replaceState).not.toHaveBeenCalled()
  })

  it('switch to Agent pack toggles the panel, syncs ?tab=agent, and tracks', () => {
    mountPanels('capability')
    render(<MethodologyTabs />)

    fireEvent.click(screen.getByRole('tab', { name: 'Agent pack' }))
    expect(panel('agent').hidden).toBe(false)
    expect(panel('capability').hidden).toBe(true)
    expect(replaceState).toHaveBeenCalledTimes(1)
    expect(String(replaceState.mock.calls[0][2])).toContain('tab=agent')
    expect(track).toHaveBeenCalledWith('rule_methodology_tab_selected', { tab: 'agent' })
  })

  it('switching back to Capability removes ?tab= and fills the formula reveal bars', () => {
    mountPanels('capability')
    render(<MethodologyTabs />)

    fireEvent.click(screen.getByRole('tab', { name: 'Agent pack' }))
    fireEvent.click(screen.getByRole('tab', { name: 'Capability rules' }))

    expect(panel('capability').hidden).toBe(false)
    expect(String(replaceState.mock.calls[1][2])).not.toContain('tab=agent')
    // A panel revealed after load force-fills its weight-bars (IO may never fire
    // for a panel that was display:none at load).
    expect(
      panel('capability').querySelector('[data-reveal]')?.classList.contains('is-visible')
    ).toBe(true)
  })

  it('keyboard: ArrowRight moves focus to the next tab; Enter activates it', () => {
    mountPanels('capability')
    render(<MethodologyTabs />)
    const cap = screen.getByRole('tab', { name: 'Capability rules' })
    const agent = screen.getByRole('tab', { name: 'Agent pack' })
    cap.focus()
    fireEvent.keyDown(cap, { key: 'ArrowRight' })
    expect(document.activeElement).toBe(agent)
    fireEvent.keyDown(agent, { key: 'Enter' })
    expect(agent.getAttribute('aria-selected')).toBe('true')
    expect(panel('agent').hidden).toBe(false)
  })

  it('a #agent-pack hashchange selects the Agent pack', () => {
    mountPanels('capability')
    render(<MethodologyTabs />)
    act(() => {
      window.history.replaceState(null, '', '/methodology#agent-pack')
      window.dispatchEvent(new Event('hashchange'))
    })
    expect(screen.getByRole('tab', { name: 'Agent pack' }).getAttribute('aria-selected')).toBe(
      'true'
    )
    expect(panel('agent').hidden).toBe(false)
  })

  it('resolves the Agent pack from ?tab=agent at first render', () => {
    mountPanels('agent')
    window.history.replaceState(null, '', '/methodology?tab=agent')
    replaceState.mockClear()
    render(<MethodologyTabs />)
    expect(screen.getByRole('tab', { name: 'Agent pack' }).getAttribute('aria-selected')).toBe(
      'true'
    )
    expect(panel('agent').hidden).toBe(false)
    // First render is the URL authority's mirror — never re-writes the URL.
    expect(replaceState).not.toHaveBeenCalled()
  })
})
