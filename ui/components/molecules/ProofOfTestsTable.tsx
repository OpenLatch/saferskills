export type ProofVerdict = 'vulnerable' | 'not_observed' | 'n_a' | 'error'

export interface ProofCheck {
  test_id: string
  family: string
  title: string
  verdict: ProofVerdict
  severity?: string
}

const RES_LABEL: Record<ProofVerdict, string> = {
  vulnerable: 'Vulnerable',
  not_observed: 'Not observed',
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
 * The Report-tab proof-of-tests table (I-5.6 §3 Report tab). Groups every applied
 * `check` by OWASP family; a passing row (`not_observed`/`n_a`) shows a ✓ result
 * chip, a vulnerable row shows a "View finding →" button (`onViewFinding(testId)`)
 * that the report wires to deep-link the Findings tab. Reuses the DS `.chk-*`
 * grammar (CheckGroupList); the full-pass variant flips to the celebratory header.
 */
export default function ProofOfTestsTable({
  checks,
  onViewFinding,
}: {
  checks: ProofCheck[]
  onViewFinding?: (testId: string) => void
}) {
  const total = checks.length
  const failed = checks.filter((c) => c.verdict === 'vulnerable').length
  const passed = total - failed
  const allPass = failed === 0
  const groups = groupByFamily(checks)

  return (
    <section className={`ar-tests${allPass ? ' pass' : ''}`} aria-label="Rules and checks applied">
      <div className="ar-tests-inner">
        <header className="ar-tests-head">
          <div className="tt-l">
            <span className="tt-badge" aria-hidden="true">
              {allPass ? '✓' : total}
            </span>
            <div className="tt-txt">
              <h3>
                {allPass ? `Passed all ${total} tests` : `Rules & checks applied · ${total} total`}
              </h3>
              <p>
                {allPass
                  ? 'clean across the full OWASP Agentic + MITRE ATLAS pack'
                  : `Passed ${passed} of ${total} tests`}
              </p>
            </div>
          </div>
          <div className="tt-meta">
            OWASP Agentic · <b>MITRE ATLAS</b>
          </div>
        </header>

        {groups.map((g) => (
          <div className="chk-group" key={g.family}>
            <div className="chk-head">
              <span className="cg-name">{g.family}</span>
              <span className="cg-meta">
                {g.rows.length - g.failed}/{g.rows.length}
                {g.failed > 0 && <b> · {g.failed} failed</b>}
              </span>
            </div>
            {g.rows.map((row) => {
              const fail = row.verdict === 'vulnerable'
              const warn = row.verdict === 'error'
              const rowClass = fail ? 'fail' : warn ? 'warn' : 'pass'
              return (
                <div className={`chk-row ${rowClass}`} key={row.test_id}>
                  <span className="chk-st" aria-hidden="true">
                    {fail ? '✕' : warn ? '!' : '✓'}
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
        ))}
      </div>
    </section>
  )
}
