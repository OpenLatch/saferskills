import ProvenanceChips, { type ProvenanceChip } from '@ui/components/atoms/ProvenanceChips'
import EmbedBadgeBox from '@ui/components/molecules/EmbedBadgeBox'

import type { AgentScanReportDetail } from '@/lib/api/agent-scan-types'

function trustLabel(labels: string[]): string {
  const parts: string[] = []
  if (labels.includes('cloud-validated')) parts.push('Cloud-validated')
  if (labels.includes('client-administered')) parts.push('Client-administered')
  return parts.length > 0 ? parts.join(' · ') : 'Cloud-validated · Client-administered'
}

/**
 * Badge band (I-5.6 §10) — the README-embed block at the foot of the report.
 * Composes the agent-variant `EmbedBadgeBox` (terminal snippet + Copy/Copy-as-HTML
 * + band-colored preview, pointing at `/badge/agent/{id}/{score}.svg` +
 * `/agents/{id}`) with a reproducibility line + provenance chips. The live SVG
 * route is Phase C; this preview matches what C will serve.
 */
export default function AgentBadgeBand({ run }: { run: AgentScanReportDetail }) {
  const score = run.score ?? 0
  const tier = run.band === 'unscoped' ? null : run.band
  const scannedDate = run.scanned_at ? run.scanned_at.slice(0, 10) : '—'

  const chips: ProvenanceChip[] = [
    {
      label: 'OWASP Agentic',
      title: 'Graded against the OWASP Top 10 for Agentic Applications (2026).',
    },
    { label: 'MITRE ATLAS', title: 'Adversarial techniques mapped to MITRE ATLAS.' },
    {
      label: trustLabel(run.trust_labels),
      title: 'The agent ran the pack on its own machine; SaferSkills graded the raw results.',
      tone: 'tier',
    },
    {
      label: 'Apache-2.0',
      title: 'The detection methodology + engine are open source under Apache-2.0.',
      tone: 'pack',
    },
  ]

  return (
    <div className="ar-badge-band">
      <div className="ar-badge-grid">
        <div className="ar-badge-l">
          <h4>Embed the badge in your README</h4>
          <p>
            A behavioral grade that re-renders from the live report — anyone can click through to
            the full methodology and trace.
          </p>
          <EmbedBadgeBox
            kind="agent"
            scanId={run.id}
            score={score}
            tier={tier}
            altPrefix="SaferSkills Agent"
          />
        </div>
        <div className="ar-badge-r">
          <div className="ar-prov-row">
            <span>Scan</span>
            <b>scn_{run.id.slice(0, 8)}</b>
          </div>
          <div className="ar-prov-row">
            <span>Pack</span>
            <b>
              {run.pack_id}@{run.pack_version}
            </b>
          </div>
          <div className="ar-prov-row">
            <span>Scanned</span>
            <b>{scannedDate}</b>
          </div>
          <ProvenanceChips chips={chips} />
        </div>
      </div>
    </div>
  )
}
