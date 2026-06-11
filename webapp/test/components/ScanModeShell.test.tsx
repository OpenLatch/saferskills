import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

// The shell test exercises tab/url/aside wiring — the heavy panes are stubbed.
vi.mock('@/components/scan/ScanConsole', () => ({
  default: () => <div data-testid="capability-pane" />,
}))
vi.mock('@/components/scan/AgentScanActivation', () => ({
  default: ({ surface }: { surface: string }) => (
    <div data-testid="agent-pane" data-surface={surface} />
  ),
}))
vi.mock('@ui/components/atoms/Toast', () => ({
  default: () => null,
  flashToast: vi.fn(),
}))

import ScanModeShell from '@/components/scan/ScanModeShell'

function panel(id: 'capability' | 'agent'): HTMLElement {
  const el = document.getElementById(`scanmode-panel-${id}`)
  if (!el) throw new Error(`panel ${id} missing`)
  return el
}

/** SSR'd methodology aside fixture (lives OUTSIDE the island — option (a)). */
function mountAside(initial: 'capability' | 'agent') {
  const aside = document.createElement('aside')
  for (const m of ['capability', 'agent'] as const) {
    const body = document.createElement('div')
    body.className = 'method-body'
    body.dataset.method = m
    body.hidden = m !== initial
    aside.appendChild(body)
  }
  document.body.appendChild(aside)
  return aside
}

describe('ScanModeShell', () => {
  let replaceState: ReturnType<typeof vi.spyOn>

  beforeEach(() => {
    vi.clearAllMocks()
    replaceState = vi.spyOn(history, 'replaceState')
  })

  afterEach(() => {
    replaceState.mockRestore()
    document.body.replaceChildren()
  })

  it('renders the capability pane by default (no replaceState on mount)', () => {
    render(<ScanModeShell />)
    expect(screen.getByRole('tab', { name: '01 Capability' }).getAttribute('aria-selected')).toBe(
      'true'
    )
    expect(panel('capability').hidden).toBe(false)
    expect(panel('agent').hidden).toBe(true)
    expect(replaceState).not.toHaveBeenCalled()
  })

  it('respects initialMode="agent" (the SSR ?mode=agent deep-link) at first render', () => {
    render(<ScanModeShell initialMode="agent" />)
    expect(screen.getByRole('tab', { name: '02 Agent' }).getAttribute('aria-selected')).toBe('true')
    expect(panel('agent').hidden).toBe(false)
    expect(panel('capability').hidden).toBe(true)
    expect(screen.getByTestId('agent-pane').getAttribute('data-surface')).toBe('scan')
    expect(replaceState).not.toHaveBeenCalled()
  })

  it('tab switch swaps the panes, syncs ?mode= via replaceState, and toggles the aside bodies', () => {
    const aside = mountAside('capability')
    render(<ScanModeShell />)

    fireEvent.click(screen.getByRole('tab', { name: '02 Agent' }))
    expect(panel('agent').hidden).toBe(false)
    expect(panel('capability').hidden).toBe(true)
    expect(replaceState).toHaveBeenCalledTimes(1)
    expect(String(replaceState.mock.calls[0][2])).toContain('mode=agent')
    // SSR'd aside bodies follow the mode
    const bodies = aside.querySelectorAll<HTMLElement>('.method-body')
    expect(bodies[0].hidden).toBe(true) // capability
    expect(bodies[1].hidden).toBe(false) // agent

    fireEvent.click(screen.getByRole('tab', { name: '01 Capability' }))
    expect(panel('capability').hidden).toBe(false)
    expect(String(replaceState.mock.calls[1][2])).not.toContain('mode=agent')
    expect(bodies[0].hidden).toBe(false)
    expect(bodies[1].hidden).toBe(true)
  })

  it('keyboard: ArrowRight moves focus to the next tab; Enter activates it', () => {
    render(<ScanModeShell />)
    const cap = screen.getByRole('tab', { name: '01 Capability' })
    const agent = screen.getByRole('tab', { name: '02 Agent' })
    cap.focus()
    fireEvent.keyDown(cap, { key: 'ArrowRight' })
    expect(document.activeElement).toBe(agent)
    fireEvent.keyDown(agent, { key: 'Enter' })
    expect(agent.getAttribute('aria-selected')).toBe('true')
    expect(panel('agent').hidden).toBe(false)
  })
})
