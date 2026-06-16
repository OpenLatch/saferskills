import SegmentedTabs from '@ui/components/atoms/SegmentedTabs'
import { useEffect, useRef, useState } from 'react'
import { track } from '@/lib/analytics'

export type MethodologyTab = 'capability' | 'agent'

const TABS = [
  { id: 'capability', label: 'Capability rules' },
  { id: 'agent', label: 'Agent pack' },
]

interface Props {
  /**
   * SSR hint from the page frontmatter. The page is prerendered, so this is
   * effectively always `'capability'` at build time — the live URL (read in the
   * useState initializer below) and the pre-paint inline script are the real
   * first-paint authority. Kept for intent + correctness if the page ever goes SSR.
   */
  initialTab?: MethodologyTab
}

/** `?tab=agent` or the `#agent-pack` hash select the Agent pack; everything else (incl.
 *  `#ss-…` / `#rules` / `#scoring-formula`) selects Capability rules. */
function resolveTab(fallback: MethodologyTab): MethodologyTab {
  if (typeof window === 'undefined') return fallback
  const params = new URLSearchParams(window.location.search)
  if (params.get('tab') === 'agent' || window.location.hash === '#agent-pack') return 'agent'
  return 'capability'
}

/**
 * MethodologyTabs (the /methodology mode control) — ONE island owning the
 * `[ Capability rules | Agent pack ]` underline SegmentedTabs. It renders ONLY
 * the control; both tab panels are server-rendered in `methodology.astro` as
 * `.method-panel[data-tab]` siblings, so the rule/pack content stays in the
 * static HTML (SEO + every deep link keep working) and this island only toggles
 * their `hidden`.
 *
 * Mirrors the toggle-siblings half of `components/scan/ScanModeShell.tsx`:
 * on switch it (a) toggles the SSR'd panels, (b) syncs `?tab=agent` ↔ none via
 * `history.replaceState` (no navigation), and (c) keeps in-page anchor jumps +
 * back/forward coherent via a `hashchange` listener. A panel revealed after load
 * gets its FormulaPanel weight-bars filled (the IntersectionObserver may never
 * fire for a panel that was `display:none` at load).
 */
export default function MethodologyTabs({ initialTab = 'capability' }: Props) {
  const [tab, setTab] = useState<MethodologyTab>(() => resolveTab(initialTab))
  const firstRender = useRef(true)

  useEffect(() => {
    // Sync the SSR'd panels (idempotent on mount — the inline script already
    // set the same split, so first paint never flashes).
    for (const el of document.querySelectorAll<HTMLElement>('.method-panel[data-tab]')) {
      const show = el.dataset.tab === tab
      el.hidden = !show
      // On an explicit switch TO a panel, fill any reveal targets the
      // IntersectionObserver may have skipped while the panel was hidden.
      if (show && !firstRender.current) {
        for (const r of el.querySelectorAll<HTMLElement>('[data-reveal]')) {
          r.classList.add('is-visible')
        }
      }
    }
    if (firstRender.current) {
      firstRender.current = false
      return
    }
    const url = new URL(window.location.href)
    if (tab === 'agent') url.searchParams.set('tab', 'agent')
    else url.searchParams.delete('tab')
    history.replaceState(null, '', url)
  }, [tab])

  // In-page anchor jumps (e.g. a `#agent-pack` link) + browser back/forward stay
  // coherent: the hash drives the tab.
  useEffect(() => {
    const onHashChange = () => {
      setTab(window.location.hash === '#agent-pack' ? 'agent' : 'capability')
    }
    window.addEventListener('hashchange', onHashChange)
    return () => window.removeEventListener('hashchange', onHashChange)
  }, [])

  return (
    <SegmentedTabs
      variant="underline"
      idBase="methodtab"
      ariaLabel="Methodology mode"
      tabs={TABS}
      value={tab}
      onChange={(id) => {
        const next = id as MethodologyTab
        setTab(next)
        track('rule_methodology_tab_selected', { tab: next })
      }}
    />
  )
}
