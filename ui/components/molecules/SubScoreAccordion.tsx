import { useState } from 'react'

import BandPill from '../atoms/BandPill'
import DotStrip from '../atoms/DotStrip'
import ScoreNumber from '../atoms/ScoreNumber'

import FindingRow, { type FindingRowProps } from './FindingRow'

type ScanTier = 'green' | 'yellow' | 'orange' | 'red' | 'unscoped'

interface Props {
  /** Display name (e.g. "Security"). */
  label: string
  /** Closed-enum sub_score key used for the PostHog event. */
  subScoreKey: 'security' | 'supply_chain' | 'maintenance' | 'transparency' | 'community'
  /** 0-100 final sub-score after critical-floor. */
  value: number
  /** Weight from the rubric (35/20/15/15/15). */
  weight: number
  /** Tier projection of `value`. */
  tier: ScanTier
  /** Whether the critical-floor cap was applied. */
  criticalFloorApplied?: boolean
  /** Findings contributing to this sub-score. */
  findings: FindingRowProps[]
  /** Open by default (e.g. security or any sub-score with criticals). */
  defaultOpen?: boolean
  /** Fires when the user expands the accordion (for telemetry). */
  onExpand?: (subScore: string) => void
}

/**
 * Collapsible per-sub-score block on /scans/<id>.
 * Header shows the score loud-num + dot strip + band pill + weight.
 * Body lists every finding via `FindingRow`.
 */
export default function SubScoreAccordion({
  label,
  subScoreKey,
  value,
  weight,
  tier,
  criticalFloorApplied,
  findings,
  defaultOpen,
  onExpand,
}: Props) {
  const [open, setOpen] = useState(!!defaultOpen)

  function handleToggle() {
    const next = !open
    setOpen(next)
    if (next && onExpand) onExpand(subScoreKey)
  }

  const findingsCount = findings.length

  return (
    <section className={`subscore-accordion${open ? ' open' : ''}`} aria-label={`${label} sub-score`}>
      <button type="button" className="subscore-accordion-head" onClick={handleToggle} aria-expanded={open}>
        <h3 className="subscore-accordion-title">{label}</h3>
        <ScoreNumber size="sm" value={value} />
        <span className="subscore-accordion-slash">/100</span>
        <DotStrip
          value={value}
          tier={value >= 80 ? 'green' : value >= 60 ? 'yellow' : value >= 40 ? 'orange' : 'red'}
        />
        {tier !== 'unscoped' ? <BandPill tier={tier} /> : <span className="band-pill unscoped">UNSCOPED</span>}
        {criticalFloorApplied ? <span className="subscore-floor">critical-floor</span> : null}
        <span className="subscore-accordion-weight">weight {weight}%</span>
        <span className="subscore-accordion-count">
          {findingsCount === 0 ? 'all clear' : `${findingsCount} finding${findingsCount === 1 ? '' : 's'}`}
        </span>
        <span className={`subscore-accordion-caret${open ? ' open' : ''}`} aria-hidden="true">
          ▾
        </span>
      </button>
      {open ? (
        <div className="subscore-accordion-body" role="region">
          {findingsCount === 0 ? (
            <p className="subscore-accordion-clear">No findings — every detector for this axis passed.</p>
          ) : (
            <ul className="subscore-accordion-findings">
              {findings.map((f) => (
                <FindingRow key={`${f.ruleId}-${f.evidence.filePath}-${f.evidence.lineStart}`} {...f} />
              ))}
            </ul>
          )}
        </div>
      ) : null}
    </section>
  )
}
