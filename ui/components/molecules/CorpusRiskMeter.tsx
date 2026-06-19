/**
 * CorpusRiskMeter — the headline figure on the `/agents` header. Two states:
 *
 * - PUBLISHED (corpus ≥ gate): the big `{pct}%` carry-a-critical rate + the claim
 *   + the inline critical definition (`.obs-figure`/`.obs-pct`/`.obs-claim`/`.obs-sub`).
 * - COLLECTING (below gate): the **methodology instrument** — instead of an apology
 *   for withholding the rate, it leads with the security substance: a confident
 *   headline + a hairline-divided 3-cell strip (pack size · framework coverage ·
 *   agents scanned) + a single quiet footnote naming the publish gate. So a
 *   small-N rate is never published, yet a security reader gets real value at any N.
 *
 * The collecting state is rendered FULL-WIDTH by the header (no risk thermometer
 * beside it — a sub-gate band split is the same skew the gate suppresses). Markup
 * is the locked "Option 2" playground design; CSS is in `page-agent-directory.css`.
 */

export default function CorpusRiskMeter({
  pctWithCritical,
  gateMet,
  corpusCount,
  gateTarget,
  packTestCount,
}: {
  /** % of the corpus carrying ≥1 critical finding; null while collecting. */
  pctWithCritical: number | null
  gateMet: boolean
  corpusCount: number
  gateTarget: number
  /** Behavioral tests in the active pack (the AS-NN count) — methodology instrument cell 1. */
  packTestCount: number
}) {
  const published = gateMet && pctWithCritical !== null

  if (published) {
    return (
      <div>
        <div className="obs-figure">
          <span className="obs-pct">{Math.round(pctWithCritical)}%</span>
          <span className="obs-claim">of assessed agents carry at least one critical finding</span>
        </div>
        <p className="obs-sub">
          Every public scan lands here, newest first — <b>not ranked</b>. A finding is{' '}
          <b>critical</b> when it can leak data, run untrusted code, or take an irreversible action
          with no guardrail.
        </p>
      </div>
    )
  }

  // Collecting — the methodology instrument (Option 2). No published rate; lead with
  // what every scanned agent is actually put through.
  return (
    <div className="obs-instr">
      <div className="obs-instr-row">
        <h2 className="obs-instr-h">
          Every agent meets the <span className="obs-instr-em">full adversarial pack</span>.
        </h2>
        <div className="obs-instr-col">
          <div className="obs-strip" role="group" aria-label="Pack coverage at a glance">
            <div className="obs-cell">
              <span className="oc-label">Behavioral tests</span>
              <span className="oc-v">{packTestCount}</span>
              <span className="oc-note">every scan</span>
            </div>
            <div className="obs-cell">
              <span className="oc-label">Mapped end-to-end</span>
              <ul className="oc-frameworks">
                <li className="ocf ocf--owasp">
                  <i aria-hidden="true" />
                  OWASP Agentic
                </li>
                <li className="ocf ocf--mitre">
                  <i aria-hidden="true" />
                  MITRE ATLAS
                </li>
              </ul>
            </div>
            <div className="obs-cell">
              <span className="oc-label">Agents scanned</span>
              <span className="oc-v">{corpusCount.toLocaleString()}</span>
              <span className="oc-note">so far</span>
            </div>
          </div>
          <p className="obs-foot">
            corpus critical-finding rate publishes at <b>{gateTarget.toLocaleString()} scans</b>
          </p>
        </div>
      </div>
    </div>
  )
}
