import ProvenanceChips, { type ProvenanceChip } from '@ui/components/atoms/ProvenanceChips'
import EmbedBadgeBox from '@ui/components/molecules/EmbedBadgeBox'

import { formatScannedAt } from '@/lib/agent/format'
import type { AgentScanReportDetail } from '@/lib/api/agent-scan-types'

/**
 * Badge band (I-5.6 §10) — the full-bleed "Embed the badge in your README" band
 * at the foot of the report (mockup `.badge-band`/`.badge-wrap`, the same layout
 * the scan report's ShareResultBand renders). Left: eyebrow + heading + pitch.
 * Right: the agent-variant `EmbedBadgeBox` README terminal (+ band-colored
 * preview), the reproducibility line, and the provenance chips. An UNLISTED run
 * gets the badge-locked variant instead (mirrors ShareResultBand — the public
 * badge SVG only exists once the report is promoted).
 */
export default function AgentBadgeBand({
  run,
  unlisted = false,
}: {
  run: AgentScanReportDetail
  unlisted?: boolean
}) {
  const score = run.score ?? 0
  const tier = run.band === 'unscoped' ? null : run.band

  if (unlisted) {
    return (
      <section className="badge-band" data-screen-label="Private status + metadata">
        <div className="container">
          <div className="badge-wrap">
            <div className="bw-l">
              <span className="sb-eyebrow">Private link</span>
              <h3>This report is unlisted</h3>
              <p>
                It is reachable only by its secret link — not indexed, not in the agent index.
                Promote it to public to make it shareable and badge-embeddable.
              </p>
            </div>
            <div className="bw-r">
              <div className="badge-locked">
                <span className="bl-lock" aria-hidden="true">
                  <svg
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                    aria-hidden="true"
                  >
                    <rect x="4" y="11" width="16" height="10" />
                    <path d="M7.5 11 V7.5 a4.5 4.5 0 0 1 9 0 V11" />
                  </svg>
                </span>
                <p>
                  A public README badge becomes available once you{' '}
                  <b>promote this report to public</b>. While unlisted, the result stays reachable
                  only by its secret link.
                </p>
              </div>
              <div className="bw-foot">
                Reproducible by re-running{' '}
                <b>
                  {run.pack_id} @ {run.pack_version}
                </b>{' '}
                against the same assembly. &nbsp;·&nbsp; scn_{run.id.slice(0, 8)} ·{' '}
                {formatScannedAt(run.scanned_at)}
              </div>
            </div>
          </div>
        </div>
      </section>
    )
  }

  const chips: ProvenanceChip[] = [
    {
      label: 'OWASP Agentic',
      title: 'Graded against the OWASP Top 10 for Agentic Applications (2026).',
      tone: 'pack',
    },
    {
      label: 'MITRE ATLAS',
      title: 'Adversarial techniques mapped to MITRE ATLAS.',
      tone: 'pack',
    },
    {
      label: `${run.pack_id} @ ${run.pack_version}`,
      title: 'The exact adversarial pack this grade is reproducible against.',
    },
    {
      label: 'Apache-2.0',
      title: 'The detection methodology + engine are open source under Apache-2.0.',
    },
  ]

  return (
    <section className="badge-band" data-screen-label="Embed this report">
      <div className="container">
        <div className="badge-wrap">
          <div className="bw-l">
            <span className="sb-eyebrow">Share this result</span>
            <h3>Embed the badge in your README</h3>
            <p>
              A live badge that always reflects the latest scan and links back to this report, so
              anyone can read the evidence behind it.
            </p>
          </div>
          <div className="bw-r">
            <EmbedBadgeBox
              kind="agent"
              scanId={run.id}
              score={score}
              tier={tier}
              altPrefix="SaferSkills"
            />
            <div className="bw-foot">
              Reproducible by re-running{' '}
              <b>
                {run.pack_id} @ {run.pack_version}
              </b>{' '}
              against the same assembly. &nbsp;·&nbsp; scn_{run.id.slice(0, 8)} ·{' '}
              {formatScannedAt(run.scanned_at)}
            </div>
            <ProvenanceChips chips={chips} />
          </div>
        </div>
      </div>
    </section>
  )
}
