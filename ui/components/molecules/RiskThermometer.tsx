/**
 * RiskThermometer — the corpus risk-distribution bar on the `/agents` header
 * (I-5.6 §12.1). Four proportional segments (Red / Orange / Yellow / Green) with
 * their percentages, the `Whole corpus · Last 3 months` window label + corpus
 * count, and the band-range legend. Segment colors are the score-band tokens
 * (never raw hex). CSS (`.therm*` / `.distrib`) is in `page-agent-directory.css`.
 */

export interface BandShare {
  pct: number
  count: number
}

export interface BandDistribution {
  red: BandShare
  orange: BandShare
  yellow: BandShare
  green: BandShare
}

const SEGMENTS: { key: keyof BandDistribution; label: string }[] = [
  { key: 'red', label: 'Red' },
  { key: 'orange', label: 'Orange' },
  { key: 'yellow', label: 'Yellow' },
  { key: 'green', label: 'Green' },
]

export default function RiskThermometer({
  distribution,
  windowLabel,
  corpusCount,
}: {
  distribution: BandDistribution
  windowLabel: string
  corpusCount: number
}) {
  return (
    <div className="therm">
      <div className="therm-head">
        <span className="therm-window">{windowLabel}</span>
        <span className="therm-count">{corpusCount.toLocaleString()} scans</span>
      </div>
      <div
        className="distrib"
        role="img"
        aria-label={SEGMENTS.map(
          (s) => `${s.label} ${Math.round(distribution[s.key]?.pct ?? 0)} percent`
        ).join(', ')}
      >
        {SEGMENTS.map((s) => {
          const pct = distribution[s.key]?.pct ?? 0
          // Fall back to an even split only when the corpus is still empty.
          const width = corpusCount > 0 ? pct : 25
          return (
            <span
              key={s.key}
              className={`distrib-seg distrib-${s.key}`}
              style={{ width: `${width}%` }}
            >
              {pct >= 8 && <span className="distrib-pct">{Math.round(pct)}%</span>}
            </span>
          )
        })}
      </div>
      <div className="therm-legend">
        <span>
          <i className="lg-sw distrib-red" aria-hidden="true" /> Red 0–39
        </span>
        <span>
          <i className="lg-sw distrib-orange" aria-hidden="true" /> Orange 40–59
        </span>
        <span>
          <i className="lg-sw distrib-yellow" aria-hidden="true" /> Yellow 60–79
        </span>
        <span>
          <i className="lg-sw distrib-green" aria-hidden="true" /> Green 80–100
        </span>
      </div>
    </div>
  )
}
