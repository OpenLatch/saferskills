import SegmentedTabs, { panelId } from '@ui/components/atoms/SegmentedTabs'
import Toast from '@ui/components/atoms/Toast'
import { useEffect, useRef, useState } from 'react'
import AgentScanActivation from './AgentScanActivation'
import ScanConsole from './ScanConsole'

export type ScanPageMode = 'capability' | 'agent'

const MODE_TABS = [
  { id: 'capability', label: '01 Capability', accent: 'teal' as const },
  { id: 'agent', label: '02 Agent', accent: 'orange' as const },
]

interface Props {
  /** SSR-resolved from `?mode=agent` (D-5.7-04) — first paint is correct. */
  initialMode?: ScanPageMode
}

/**
 * The /scan mode shell (I-5.7 plan 03 Module 2) — ONE island owning the
 * `[01 Capability | 02 Agent]` SegmentedTabs (genuine tabs-over-panels) plus
 * both panes: the existing `ScanConsole` (capability) and the
 * `AgentScanActivation` activation surface (agent).
 *
 * On tab switch it (a) swaps the panes (opacity-only crossfade via
 * `@starting-style` in page-scan-submit.css — an interruptible transition, no
 * keyframes), (b) syncs `?mode=agent` ↔ none with `history.replaceState` (no
 * navigation, back-button stays sane), and (c) toggles the SSR'd methodology
 * aside bodies (`.method-body[data-method]`, rendered statically by
 * `ScanMethodologyPreview.astro` — option (a): zero extra hydration).
 *
 * A run is minted ONLY on the explicit "Generate my scan prompt" click —
 * never on tab switch (plan 03 REJECTED list).
 */
export default function ScanModeShell({ initialMode = 'capability' }: Props) {
  const [mode, setMode] = useState<ScanPageMode>(initialMode)
  const firstRender = useRef(true)

  useEffect(() => {
    // Sync the SSR'd aside bodies (idempotent on mount — Astro already
    // rendered the initialMode split, so first paint never flashes).
    for (const el of document.querySelectorAll<HTMLElement>('.method-body[data-method]')) {
      el.hidden = el.dataset.method !== mode
    }
    if (firstRender.current) {
      firstRender.current = false
      return
    }
    const url = new URL(window.location.href)
    if (mode === 'agent') url.searchParams.set('mode', 'agent')
    else url.searchParams.delete('mode')
    history.replaceState(null, '', url)
  }, [mode])

  return (
    <>
      <SegmentedTabs
        variant="segmented"
        idBase="scanmode"
        ariaLabel="What to scan"
        tabs={MODE_TABS}
        value={mode}
        onChange={(id) => setMode(id as ScanPageMode)}
      />
      <div className="modepanel">
        <div
          id={panelId('scanmode', 'capability')}
          role="tabpanel"
          aria-labelledby="scanmode-tab-capability"
          className="mp-body"
          hidden={mode !== 'capability'}
        >
          <ScanConsole />
        </div>
        <div
          id={panelId('scanmode', 'agent')}
          role="tabpanel"
          aria-labelledby="scanmode-tab-agent"
          className="mp-body"
          hidden={mode !== 'agent'}
        >
          <AgentScanActivation surface="scan" />
        </div>
      </div>
      {/* Shell-level Toast root: both panes stay mounted (hidden), and the
          module-level flashToast binds to the LAST mounted <Toast/> — this one,
          which is never inside a [hidden] subtree, so toasts always render. */}
      <Toast />
    </>
  )
}
