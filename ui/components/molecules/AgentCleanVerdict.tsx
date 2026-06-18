export interface AgentCleanVerdictProps {
  /** Behavioral tests the agent passed (numerator of the headline ratio). */
  testsPassed: number
  /** Total behavioral tests run in the pack. */
  totalTests: number
  /** Distinct OWASP/MITRE risk families probed (derived from the run's checks). */
  familiesProbed: number
  /** Reproducibility line, e.g. `saferskills-agent-baseline @ 2026.06.09`. */
  packLabel: string
}

/**
 * Findings-tab empty state for a clean pass — the agent flagged **zero**
 * findings. A composed verdict panel (hex-cap seal · verdict eyebrow · headline ·
 * evidence ledger of the run's real numbers · reproducibility line) replacing the
 * earlier oversized inline checkmark. Reuses the shared `.ar-empty` panel chrome
 * (DS-owned in `components.css`) in its `--pass` variant; zero new design language.
 * Fully presentational — the webapp passes the run's derived counts.
 */
export default function AgentCleanVerdict({
  testsPassed,
  totalTests,
  familiesProbed,
  packLabel,
}: AgentCleanVerdictProps) {
  return (
    <section className="ar-empty ar-empty--pass" aria-label="Clean pass — no findings">
      <div className="cv-head">
        <span className="cv-seal" aria-hidden="true">
          <svg viewBox="0 0 48 48" width="48" height="48" fill="none" role="presentation">
            <path className="cv-seal-hex" d="M24 3 L42 13.6 L42 34.4 L24 45 L6 34.4 L6 13.6 Z" />
            <path className="cv-seal-check" d="M15.5 24.4 L21.5 30.4 L33 18.2" />
          </svg>
        </span>
        <div className="cv-headtext">
          <p className="cv-eyebrow">
            Verdict · <b>Clean pass</b>
          </p>
          <h3 className="cv-title">No findings.</h3>
          <p className="cv-lede">
            This agent withstood every adversarial probe in the OWASP Agentic + MITRE ATLAS
            pack — there is nothing to remediate.
          </p>
        </div>
      </div>

      <div className="cv-ledger">
        <div className="cv-stat">
          <span className="cv-num">
            {testsPassed}
            <span className="cv-num-d">/{totalTests}</span>
          </span>
          <span className="cv-lab">Tests passed</span>
        </div>
        <div className="cv-stat">
          <span className="cv-num">{familiesProbed}</span>
          <span className="cv-lab">Risk families probed</span>
        </div>
        <div className="cv-stat">
          <span className="cv-num cv-num--clear">0</span>
          <span className="cv-lab">Vulnerable behaviors</span>
        </div>
      </div>

      <p className="cv-prov">
        <span className="cv-prov-k">Reproducible against</span> {packLabel}
      </p>
    </section>
  )
}
