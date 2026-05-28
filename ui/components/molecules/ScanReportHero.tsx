import type { ReactNode } from 'react'

import BandPill from '../atoms/BandPill'
import DotStrip from '../atoms/DotStrip'
import Eyebrow from '../atoms/Eyebrow'
import ScoreNumber from '../atoms/ScoreNumber'

type ScanTier = 'green' | 'yellow' | 'orange' | 'red' | 'unscoped'

interface SubScoreEntry {
  label: string
  key: string
  value: number
  weight: number
  finalSubScore?: number
  criticalFloorApplied?: boolean
}

interface Props {
  /** 0-100. */
  score: number
  tier: ScanTier
  /** Mono uppercase eyebrow over the score (e.g. "AGGREGATE"). */
  eyebrow?: string
  /** Optional “↑ +25 since first scan” style annotation. */
  deltaLabel?: string
  /** Sub-score progress bars rendered below the hero (one per row). */
  subScores?: SubScoreEntry[]
  /** Optional install command box rendered to the right of the score. */
  rightSlot?: ReactNode
  /** Critical-floor / aggregate-math panel rendered to the far right. */
  mathSlot?: ReactNode
}

/**
 * 3-column hero band for the complete /scans/<id> view.
 * Vocabulary: `mockups/hifi/app-pages.css::.report-hero`.
 */
export default function ScanReportHero({
  score,
  tier,
  eyebrow = 'AGGREGATE',
  deltaLabel,
  subScores,
  rightSlot,
  mathSlot,
}: Props) {
  return (
    <section className="report-hero" aria-label="Scan report hero">
      <div className="report-hero-grid">
        <div className="report-hero-score">
          <Eyebrow withRule>{eyebrow}</Eyebrow>
          <div className="report-hero-score-row">
            <ScoreNumber size="hero" value={score} />
            <span className="report-hero-score-slash">/100</span>
          </div>
          <div className="report-hero-meta">
            <DotStrip
              value={score}
              tier={
                score >= 80 ? 'green' : score >= 60 ? 'yellow' : score >= 40 ? 'orange' : 'red'
              }
            />
            {tier !== 'unscoped' ? <BandPill tier={tier} /> : <span className="band-pill unscoped">UNSCOPED</span>}
          </div>
          {deltaLabel ? <p className="report-hero-delta">{deltaLabel}</p> : null}
        </div>
        {rightSlot ? <div className="report-hero-right">{rightSlot}</div> : null}
        {mathSlot ? <div className="report-hero-math">{mathSlot}</div> : null}
      </div>
      {subScores && subScores.length > 0 ? (
        <div className="report-hero-subscores" role="list">
          {subScores.map((row) => {
            const visualPct = row.finalSubScore ?? row.value
            return (
              <div
                key={row.key}
                role="listitem"
                className={`report-hero-subscore-row${row.criticalFloorApplied ? ' has-floor' : ''}`}
              >
                <span className="report-hero-subscore-label">{row.label}</span>
                <div className="report-hero-subscore-bar">
                  <div
                    className="report-hero-subscore-fill"
                    style={{ width: `${Math.max(0, Math.min(100, visualPct))}%` }}
                  />
                </div>
                <span className="report-hero-subscore-value">
                  <strong>{row.value}</strong>
                  <span className="report-hero-subscore-weight"> weight {row.weight}%</span>
                </span>
              </div>
            )
          })}
        </div>
      ) : null}
    </section>
  )
}
