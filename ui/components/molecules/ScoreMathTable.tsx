export interface ScoreMathModifier {
  /** Test id of the contributing finding, e.g. `AS-06`. */
  testId: string
  /** Severity label shown as the row sublabel. */
  severity: string
  /** Signed score delta (negative = penalty). */
  delta: number
  /** Emphasize this row (the finding whose card this table sits in). */
  emphasized?: boolean
}

export interface ScoreMathTableProps {
  /** The assembled-agent starting score (the scale top). */
  base: number
  /** One signed-modifier row per scored finding (from the report `score_breakdown`). */
  modifiers: ScoreMathModifier[]
  /** Worst-finding cap row — present only when the report ceiling was applied. */
  cap?: { label: string; value: number } | null
  /** The reconciled headline score. */
  finalScore: number
  finalLabel?: string
}

function fmtDelta(n: number): string {
  return n > 0 ? `+${n}` : `${n}`
}

/**
 * Per-finding "How the score moved" table (I-5.6 §6). A signed-modifier ledger —
 * base row + one row per scored finding + the worst-finding cap (when applied) +
 * the reconciled final. Numbers are sourced verbatim from the report-level
 * `score_breakdown` (the single source of truth); nothing is recomputed here.
 * Reuses the `.score-math` / `.sm-row` grammar (DS-owned CSS in components.css).
 */
export default function ScoreMathTable({
  base,
  modifiers,
  cap = null,
  finalScore,
  finalLabel = 'Final score',
}: ScoreMathTableProps) {
  return (
    <div className="score-math" aria-label="How the score moved">
      <div className="sm-row base">
        <span className="sm-f">
          <b>Base</b> <span>assembled-agent start</span>
        </span>
        <span className="d">{base}</span>
      </div>
      {modifiers.map((m) => (
        <div className={`sm-row${m.emphasized ? ' me' : ''}`} key={m.testId}>
          <span className="sm-f">
            <b>{m.testId}</b> <span>{m.severity}</span>
          </span>
          <span className={`d ${m.delta < 0 ? 'neg' : 'pos'}`}>{fmtDelta(m.delta)}</span>
        </div>
      ))}
      {cap ? (
        <div className="sm-row cap">
          <span className="sm-f">
            <b>{cap.label}</b> <span>overrides the weighted average</span>
          </span>
          <span className="d">→ {cap.value}</span>
        </div>
      ) : null}
      <div className="sm-row total">
        <span className="sm-f">
          <b>{finalLabel}</b>
        </span>
        <span className="d">{finalScore}</span>
      </div>
    </div>
  )
}
