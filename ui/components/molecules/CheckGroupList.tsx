export interface CheckGroupCategory {
  /** Sub-score key (e.g. `security`) — groups findings + indexes `subScores`. */
  key: string
  /** Display name (e.g. `Security`). */
  name: string
}

export interface CheckGroupFinding {
  id: string
  ruleId: string
  severity: 'info' | 'low' | 'medium' | 'high' | 'critical'
  /** Which category this finding rolls up under (matches `category.key`). */
  subScore: string
  filePath: string
  lineStart: number
}

interface Props {
  /** Score axes in display order — one `.chk-group` per category. */
  categories: CheckGroupCategory[]
  /** `{ key → 0–100 }` sub-score map, shown in each group's meta line. */
  subScores: Record<string, number>
  /** Flat finding list; grouped here by `subScore`. */
  findings: CheckGroupFinding[]
  /**
   * Noun for the empty-category copy ("No findings in this category for
   * <noun>."). The item report uses `"the latest scan"`; the single-capability
   * upload report uses the default `"this scan"`.
   */
  emptyScanNoun?: string
}

type RowStatus = 'pass' | 'warn' | 'fail'

/**
 * Compact grouped pass/warn/fail checklist for a capability's findings, shared
 * by the item-detail report (`ItemTabs`) and the single-capability upload
 * report (`CapabilityReportTabs`).
 *
 * Intentionally DISTINCT from the DS `FindingRow`: `FindingRow` is the
 * link-rich evidence `<li>` for the repo-level report (severity pill, rule
 * link, GitHub evidence href); `CheckGroupList` is the terse grouped checklist
 * that shows a green "all passed" row per empty category and a warn/fail glyph
 * per finding. The two are not interchangeable — see
 * `.claude/rules/design-system.md` § FindingRow vs CheckGroupList.
 */
export default function CheckGroupList({
  categories,
  subScores,
  findings,
  emptyScanNoun = 'this scan',
}: Props) {
  return (
    <>
      <p className="score-checks-head">Findings &amp; checks · {findings.length} flagged</p>
      {categories.map((c) => {
        const catFindings = findings.filter((f) => f.subScore === c.key)
        return (
          <div className="chk-group" key={c.key}>
            <div className="chk-head">
              <span className="cg-name">{c.name}</span>
              <span className="cg-meta">
                score {subScores[c.key] ?? 0} · {catFindings.length} finding
                {catFindings.length === 1 ? '' : 's'}
              </span>
            </div>
            {catFindings.length === 0 ? (
              <CheckRow
                status="pass"
                glyph="✓"
                id="—"
                title={`All ${c.name.toLowerCase()} checks passed`}
                detail={`No findings in this category for ${emptyScanNoun}.`}
                result="pass"
              />
            ) : (
              catFindings.map((f) => {
                const fail = f.severity === 'high' || f.severity === 'critical'
                return (
                  <CheckRow
                    key={f.id}
                    status={fail ? 'fail' : 'warn'}
                    glyph={fail ? '✕' : '⚠'}
                    id={f.ruleId}
                    title={`${f.severity} finding`}
                    detail={`${f.filePath}:${f.lineStart}`}
                    result={f.severity}
                  />
                )
              })
            )}
          </div>
        )
      })}
    </>
  )
}

/** Single check row: status glyph · rule id · title+detail · result chip. */
function CheckRow({
  status,
  glyph,
  id,
  title,
  detail,
  result,
}: {
  status: RowStatus
  glyph: string
  id: string
  title: string
  detail: string
  result: string
}) {
  return (
    <div className={`chk-row ${status}`}>
      <span className="chk-st">{glyph}</span>
      <span className="chk-id">{id}</span>
      <span className="chk-tt">
        {title}
        <em>{detail}</em>
      </span>
      <span className="chk-res">{result}</span>
    </div>
  )
}
