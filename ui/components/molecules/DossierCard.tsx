import CapabilityStack, { type CapabilityTally } from '../atoms/CapabilityStack'
import DotStrip from '../atoms/DotStrip'
import RuntimeMonogram from '../atoms/RuntimeMonogram'
import ScoreNumber from '../atoms/ScoreNumber'
import SeverityPill from '../atoms/SeverityPill'

export type DossierBand = 'green' | 'yellow' | 'orange' | 'red' | 'unscoped'

export interface DossierFindings {
  critical: number
  high: number
  info: number
  total: number
}

export interface DossierCardProps {
  /** Display name (H-row). */
  agentName: string
  runtime: string
  score: number | null
  band: DossierBand
  /** ISO scanned-at; rendered as a date (hydration-safe — no relative `Date.now`). */
  scannedAt: string | null
  capabilityTally: CapabilityTally
  findings: DossierFindings
  trustTier: string | null
  /** `/agents/{id}` report link. */
  href: string
  /** The newest card carries the live pulse dot. */
  isNewest?: boolean
}

/**
 * DossierCard — one agent in the `/agents` directory grid (I-5.6 §12.3). Name +
 * scan date (live pulse on the newest), score row (big score + 10-dot meter +
 * capability stack), findings row (severity counts or `✓ No findings`), and a foot
 * (runtime monogram + name · trust tier). A critical-bearing card gets the
 * `.crit-row` accent. The whole card links to `/agents/{id}`. CSS (`.dossier` /
 * `.d-*`) is in `page-agent-directory.css`.
 */
export default function DossierCard({
  agentName,
  runtime,
  score,
  band,
  scannedAt,
  capabilityTally,
  findings,
  trustTier,
  href,
  isNewest = false,
}: DossierCardProps) {
  const hasCritical = findings.critical > 0
  const dotTier = band === 'unscoped' ? null : band
  const date = scannedAt ? scannedAt.slice(0, 10) : '—'

  return (
    <a className={`dossier ${hasCritical ? 'crit-row' : ''}`.trim()} href={href}>
      <div className="d-top">
        <span className="d-name">{agentName}</span>
        <span className="d-time">
          {isNewest && <span className="pulse" aria-hidden="true" />}
          <time dateTime={scannedAt ?? undefined}>{date}</time>
        </span>
      </div>

      <div className="d-score-row">
        <span className="d-score">
          <ScoreNumber value={score ?? 0} size="lg" />
        </span>
        {dotTier && <DotStrip value={score ?? 0} tier={dotTier} className="d-dots" />}
        <CapabilityStack tally={capabilityTally} className="d-caps" />
      </div>

      <div className="d-find">
        {findings.total > 0 ? (
          <>
            {findings.critical > 0 && (
              <SeverityPill severity="critical" label={`${findings.critical} critical`} />
            )}
            {findings.high > 0 && <SeverityPill severity="high" label={`${findings.high} high`} />}
            {findings.info > 0 && <SeverityPill severity="info" label={`${findings.info} info`} />}
          </>
        ) : (
          <span className="d-clean">✓ No findings</span>
        )}
      </div>

      <div className="d-foot">
        <RuntimeMonogram runtime={runtime} showName />
        {trustTier && <span className="d-trust">· {trustTier}</span>}
      </div>
    </a>
  )
}
