export interface ScoreCategoryRow {
  /** Sub-score key (e.g. `security`) — indexes into `subScores`. */
  key: string
  /** Display name (e.g. `Security`). */
  name: string
  /** Locked aggregate weight as a percentage (0–100). */
  weight: number
  /** Short descriptive blurb of the detectors in this axis. */
  detectors: string
}

interface Props {
  /** Score axes in display order. The webapp passes `SCORE_CATEGORIES`
   *  (structurally compatible) — `ui/` never imports it directly. */
  categories: ScoreCategoryRow[]
  /** `{ key → 0–100 }` sub-score map for the scanned capability. */
  subScores: Record<string, number>
}

/**
 * The score-breakdown table shared by the item-detail report (`ItemTabs`) and
 * the single-capability upload report (`CapabilityReportTabs`). Pure render —
 * one row per category showing weight, the 0–100 category score with its bar,
 * and the weighted contribution (`score × weight / 100`).
 *
 * The `sk-bar-grow` entrance animation on `.sc-bar .track i` lives in
 * `ui/styles/components.css` alongside `.score-cats` (DS-owned CSS).
 */
export default function ScoreBreakdownTable({ categories, subScores }: Props) {
  return (
    <div className="score-cats">
      <div className="sc-row sc-head">
        <span>Category</span>
        <span>Weight</span>
        <span>Category score</span>
        <span style={{ textAlign: 'right' }}>Contribution</span>
      </div>
      {categories.map((c) => {
        const cs = subScores[c.key] ?? 0
        const contrib = ((cs * c.weight) / 100).toFixed(1)
        return (
          <div className="sc-row" key={c.key}>
            <div className="sc-cat">
              <b>{c.name}</b>
              <span>{c.detectors}</span>
            </div>
            <div className="sc-weight">{c.weight}%</div>
            <div className="sc-bar">
              <span className="num">{cs}</span>
              <span className="track">
                <i style={{ width: `${cs}%` }} />
              </span>
            </div>
            <div className="sc-contrib">
              <b>{contrib}</b> pts
            </div>
          </div>
        )
      })}
    </div>
  )
}
