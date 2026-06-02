import { type KeyboardEvent, useRef } from 'react'

import { bandFromTier } from '@/components/catalog/constants'
import type { CapabilityKind, CapabilityRow } from '@/lib/api/scans'

/**
 * File-tab strip for a multi-file upload report (I-3.5). One tab per scanned
 * file — kind glyph + filename + tier dot + tier-colored score, active underline
 * in the tier color. A page-specific `role="tablist"` (the `.mf-*` vocabulary,
 * CSS in `page-scan-report.css`), mirroring the DS `SegmentedTabs` keyboard model
 * (←/→/↑/↓/Home/End) with automatic activation: moving focus switches the file.
 */

const KIND_GLYPH: Record<CapabilityKind, string> = {
  skill: 'SK',
  mcp_server: 'MCP',
  hook: 'HK',
  rules: 'RU',
  plugin: 'PL',
}

interface Props {
  caps: CapabilityRow[]
  active: number
  onSelect: (i: number) => void
  /** Id of the tabpanel each tab controls (the shared per-file body). */
  panelId: string
  /** Id prefix for each tab so the panel can be `aria-labelledby` the active tab. */
  tabIdBase: string
}

export default function FileTabStrip({ caps, active, onSelect, panelId, tabIdBase }: Props) {
  const refs = useRef<(HTMLButtonElement | null)[]>([])

  function select(i: number) {
    const n = caps.length
    const idx = ((i % n) + n) % n
    onSelect(idx)
    refs.current[idx]?.focus()
  }

  function onKeyDown(e: KeyboardEvent<HTMLButtonElement>, i: number) {
    switch (e.key) {
      case 'ArrowRight':
      case 'ArrowDown':
        e.preventDefault()
        select(i + 1)
        break
      case 'ArrowLeft':
      case 'ArrowUp':
        e.preventDefault()
        select(i - 1)
        break
      case 'Home':
        e.preventDefault()
        select(0)
        break
      case 'End':
        e.preventDefault()
        select(caps.length - 1)
        break
    }
  }

  return (
    <section className="mf-nav" aria-label="Uploaded files">
      <div className="container">
        <div className="mf-tabs" role="tablist" aria-label="Scanned files">
          {caps.map((cap, i) => {
            const band = bandFromTier(cap.tier, cap.aggregate_score) ?? 'r'
            const selected = i === active
            return (
              <button
                key={cap.scan_id}
                ref={(el) => {
                  refs.current[i] = el
                }}
                type="button"
                role="tab"
                id={`${tabIdBase}-${i}`}
                aria-controls={panelId}
                aria-selected={selected}
                tabIndex={selected ? 0 : -1}
                className={`mf-tab band-${band}${selected ? ' on' : ''}`}
                onClick={() => select(i)}
                onKeyDown={(e) => onKeyDown(e, i)}
              >
                <span className="mf-glyph">{KIND_GLYPH[cap.kind]}</span>
                <span className="mf-name">{cap.name}</span>
                <span className={`mf-dot dot-${band}`} aria-hidden="true">
                  ●
                </span>
                <span className="mf-score">{cap.aggregate_score}</span>
              </button>
            )
          })}
        </div>
      </div>
    </section>
  )
}
