import type { CSSProperties } from 'react'

export interface WeightRow {
  /** Sub-score / category label, e.g. "Security". */
  label: string
  /** Integer weight percent (0–100) — rendered as the loud `%` column + bar fill. */
  weight: number
  /** Optional mono sub-label under the name (e.g. example rule_ids). */
  rules?: string
}

interface Props {
  rows: ReadonlyArray<WeightRow>
  /**
   * When false, drops the outer hairline frame so the bars can sit inside an
   * existing panel without a nested-card border. Default true (standalone box).
   */
  framed?: boolean
  className?: string
}

/**
 * WeightBars — the 5-sub-score "how it's weighted" visual shared by the /scan
 * methodology preview and the /methodology formula panel (DS-first: one source,
 * not a per-page copy).
 *
 * Each row is name + loud `%` + a track whose fill is sized with
 * `transform: scaleX(--wb-frac)` (GPU-friendly, so a consumer can animate the
 * fill in on reveal without a width reflow). CSS lives in
 * `ui/styles/components.css` under `.weight-bars`.
 */
export default function WeightBars({ rows, framed = true, className }: Props) {
  return (
    <div className={`weight-bars${framed ? '' : ' weight-bars--bare'}${className ? ` ${className}` : ''}`}>
      {rows.map((r) => (
        <div className="wb-row" key={r.label}>
          <div className="wb-name">
            <b>{r.label}</b>
            {r.rules ? <span className="wb-rule">{r.rules}</span> : null}
          </div>
          <div className="wb-wt">{r.weight}%</div>
          <div className="wb-bar">
            <i
              className="wb-fill"
              style={{ '--wb-frac': r.weight / 100 } as CSSProperties}
              aria-hidden="true"
            />
          </div>
        </div>
      ))}
    </div>
  )
}
