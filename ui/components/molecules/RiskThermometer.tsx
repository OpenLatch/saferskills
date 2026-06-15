/**
 * RiskThermometer — the corpus risk-distribution bar on the `/agents` header
 * (I-5.6 §12.1). Four proportional segments (Red / Orange / Yellow / Green) with
 * their percentages, the `Risk distribution · Whole corpus · Last 3 months` head
 * + corpus count, and the band-range legend. Markup mirrors the locked mockup
 * (`.therm-wrap` / `.therm-head` / `.therm` / `.seg` / `.therm-legend`); segment
 * colors are the score-band tokens. CSS is in `page-agent-directory.css`.
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

const SEGMENTS: { key: keyof BandDistribution; cls: string; label: string; range: string }[] = [
  { key: 'red', cls: 'r', label: 'Red', range: '0–39' },
  { key: 'orange', cls: 'o', label: 'Orange', range: '40–59' },
  { key: 'yellow', cls: 'y', label: 'Yellow', range: '60–79' },
  { key: 'green', cls: 'g', label: 'Green', range: '80–100' },
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
    <div className="therm-wrap">
      <div className="therm-head">
        <span>Risk distribution · {windowLabel}</span>
        <span>
          <b>{corpusCount.toLocaleString()}</b> agents
        </span>
      </div>
      <div
        className="therm"
        role="img"
        aria-label={SEGMENTS.map(
          (s) => `${s.label} ${Math.round(distribution[s.key]?.pct ?? 0)} percent`
        ).join(', ')}
      >
        {SEGMENTS.map((s) => {
          const pct = distribution[s.key]?.pct ?? 0
          // Fall back to an even split only when the corpus is still empty.
          const flex = corpusCount > 0 ? pct : 25
          return (
            <div key={s.key} className={`seg ${s.cls}`} style={{ flex }}>
              {pct >= 8 && <span className="pct">{Math.round(pct)}%</span>}
            </div>
          )
        })}
      </div>
      <div className="therm-legend">
        {SEGMENTS.map((s) => (
          <div key={s.key}>
            <i className={s.cls} aria-hidden="true" />
            {s.label} · {s.range}
          </div>
        ))}
      </div>
    </div>
  )
}
