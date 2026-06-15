export type ProofVerdict = 'vulnerable' | 'not_observed' | 'n_a' | 'error'

export interface ProofCheck {
  test_id: string
  family: string
  title: string
  verdict: ProofVerdict
  severity?: string
}

const RES_LABEL: Record<ProofVerdict, string> = {
  vulnerable: 'Fail',
  not_observed: 'Pass',
  n_a: 'N/A',
  error: 'Error',
}

interface FamilyGroup {
  family: string
  rows: ProofCheck[]
  failed: number
}

function groupByFamily(checks: ProofCheck[]): FamilyGroup[] {
  const order: string[] = []
  const map = new Map<string, ProofCheck[]>()
  for (const c of checks) {
    if (!map.has(c.family)) {
      map.set(c.family, [])
      order.push(c.family)
    }
    map.get(c.family)?.push(c)
  }
  return order.map((family) => {
    const rows = map.get(family) ?? []
    return { family, rows, failed: rows.filter((r) => r.verdict === 'vulnerable').length }
  })
}

/**
 * The Report-tab proof-of-tests table (I-5.6 §3 Report tab). Mirrors the locked
 * mockup: a `Rules & checks applied · N total` checks-head, then one bordered
 * `.chk-group` per OWASP family — group head carries `{n} failed · {p}/{t} passed`,
 * a passing row shows the ✓ + `PASS` chip, a vulnerable row the ✗ + a red
 * `View finding →` button (`onViewFinding(testId)`) that the report wires to
 * deep-link the Findings tab. Reuses the DS `.chk-*` grammar (CheckGroupList).
 */
export default function ProofOfTestsTable({
  checks,
  onViewFinding,
}: {
  checks: ProofCheck[]
  onViewFinding?: (testId: string) => void
}) {
  const total = checks.length
  const allPass = checks.every((c) => c.verdict !== 'vulnerable')
  const groups = groupByFamily(checks)

  return (
    <section className={`ar-tests${allPass ? ' pass' : ''}`} aria-label="Rules and checks applied">
      <p className="score-checks-head">Rules &amp; checks applied · {total} total</p>

      {groups.map((g) => {
        const passedRows = g.rows.length - g.failed
        return (
          <div className="chk-group" key={g.family}>
            <div className="chk-head">
              <span className="cg-name">{g.family}</span>
              <span className="cg-meta">
                {g.failed > 0 ? (
                  <>
                    <b>{g.failed} failed</b> · {passedRows}/{g.rows.length} passed
                  </>
                ) : (
                  <>
                    {passedRows}/{g.rows.length} passed
                  </>
                )}
              </span>
            </div>
            {g.rows.map((row) => {
              const fail = row.verdict === 'vulnerable'
              const warn = row.verdict === 'error'
              const rowClass = fail ? 'fail' : warn ? 'warn' : 'pass'
              return (
                <div className={`chk-row ${rowClass}`} key={row.test_id}>
                  <span className="chk-st" aria-hidden="true">
                    {fail ? '✗' : warn ? '!' : '✓'}
                  </span>
                  <span className="chk-id">{row.test_id}</span>
                  <span className="chk-tt">{row.title}</span>
                  {fail ? (
                    <button
                      type="button"
                      className="chk-gobtn"
                      onClick={() => onViewFinding?.(row.test_id)}
                    >
                      <span className="sev-dot" aria-hidden="true" />
                      View finding →
                    </button>
                  ) : (
                    <span className="chk-res">{RES_LABEL[row.verdict]}</span>
                  )}
                </div>
              )
            })}
          </div>
        )
      })}
    </section>
  )
}
