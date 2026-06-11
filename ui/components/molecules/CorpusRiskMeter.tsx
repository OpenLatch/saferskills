/**
 * CorpusRiskMeter — the headline risk figure on the `/agents` header (I-5.6 §12.1,
 * D-5.6-07). When the public corpus has reached the gate it shows the big
 * `{pct}%` + the claim + the inline critical definition. Below the gate it shows
 * the COLLECTING state instead — the `%` blanks to `—`, with the hold copy + a
 * progress bar toward the gate target — so a small-N rate is never published.
 * CSS (`.obs-*`) is in `page-agent-directory.css`.
 */

export default function CorpusRiskMeter({
  pctWithCritical,
  gateMet,
  corpusCount,
  gateTarget,
}: {
  /** % of the corpus carrying ≥1 critical finding; null while collecting. */
  pctWithCritical: number | null
  gateMet: boolean
  corpusCount: number
  gateTarget: number
}) {
  const published = gateMet && pctWithCritical !== null
  const progress = gateTarget > 0 ? Math.min(100, (corpusCount / gateTarget) * 100) : 0

  return (
    <div className={`obs-figure-wrap ${published ? '' : 'is-collecting'}`.trim()}>
      <div className="obs-eyebrow">Agents · /agents · the public corpus</div>
      {published ? (
        <>
          <div className="obs-figure">
            <span className="obs-pct">{Math.round(pctWithCritical)}%</span>
          </div>
          <p className="obs-claim">of assessed agents carry at least one critical finding</p>
          <p className="obs-sub">
            <b>Critical:</b> can leak data, run untrusted code, or take an irreversible action with
            no guardrail.
          </p>
        </>
      ) : (
        <div className="obs-collecting">
          <div className="obs-figure">
            <span className="obs-pct obs-pct--blank" aria-hidden="true">
              —
            </span>
          </div>
          <p className="obs-claim">
            collecting data — the rate is gated until the sample is large enough to publish
          </p>
          <p className="obs-sub">
            We hold the rate back until at least <b>{gateTarget.toLocaleString()}</b> public agent
            scans land, so a small-sample number can't become the story.
          </p>
          <div className="obs-gate">
            <span className="obs-gate-label">
              gated until n ≥ {gateTarget.toLocaleString()} · {corpusCount.toLocaleString()}/
              {gateTarget.toLocaleString()} so far
            </span>
            <div
              className="obs-gate-rail"
              role="progressbar"
              aria-valuemin={0}
              aria-valuemax={gateTarget}
              aria-valuenow={corpusCount}
              aria-label="Corpus progress toward the publish gate"
            >
              <span className="obs-gate-fill" style={{ width: `${progress}%` }} />
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
