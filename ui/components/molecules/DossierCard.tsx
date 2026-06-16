import CapabilityStack, { type CapabilityTally } from '../atoms/CapabilityStack'
import DotStrip from '../atoms/DotStrip'
import RuntimeMonogram from '../atoms/RuntimeMonogram'

export type DossierBand = 'green' | 'yellow' | 'orange' | 'red' | 'unscoped'

export interface DossierFindings {
  critical: number
  high: number
  info: number
  total: number
}

const BAND_CLASS: Record<DossierBand, string> = {
  green: 'g',
  yellow: 'y',
  orange: 'o',
  red: 'r',
  unscoped: '',
}

/** `4h ago` / `2d ago` relative scan time (from a stable `now` so SSR + hydration agree). */
function ago(scannedAt: string | null, now: number): string {
  if (!scannedAt) return '—'
  const t = Date.parse(scannedAt)
  if (Number.isNaN(t)) return '—'
  const hours = Math.max(1, Math.round((now - t) / 3_600_000))
  return hours < 24 ? `${hours}h ago` : `${Math.round(hours / 24)}d ago`
}

export interface DossierCardProps {
  /** Display name (H-row). */
  agentName: string
  runtime: string
  score: number | null
  band: DossierBand
  /** ISO scanned-at; rendered relative (`4h ago`) off the page-stable `now`. */
  scannedAt: string | null
  /** Page-stable epoch ms captured once per render (SSR + hydration agree). */
  now: number
  capabilityTally: CapabilityTally
  findings: DossierFindings
  /** `/agents/{id}` report link. */
  href: string
  /** The newest card carries the live pulse dot. */
  isNewest?: boolean
}

/**
 * DossierCard — one agent in the `/agents` directory grid (I-5.6 §12.3). Markup
 * mirrors the locked mockup dossier card: band-edged frame (`.dossier.{g|y|o|r}`),
 * name + relative time (live pulse on the newest), score row (ink `{score}/100` +
 * 10-dot meter + right-aligned capability stack), findings row (severity chips or
 * `✓ No findings`), and a paper-deep foot (runtime monogram + name).
 * A critical-bearing card gets the `.crit-row` red frame. CSS (`.dossier` /
 * `.d-*`) is in `page-agent-directory.css`.
 */
export default function DossierCard({
  agentName,
  runtime,
  score,
  band,
  scannedAt,
  now,
  capabilityTally,
  findings,
  href,
  isNewest = false,
}: DossierCardProps) {
  const hasCritical = findings.critical > 0
  const dotTier = band === 'unscoped' ? null : band

  return (
    <a
      className={`dossier ${BAND_CLASS[band]}${hasCritical ? ' crit-row' : ''}`.trim()}
      href={href}
    >
      <div className="d-top">
        <div>
          <div className="d-name">{agentName}</div>
        </div>
        <div className="d-time">
          {isNewest && <span className="pulse" aria-hidden="true" />}
          <time dateTime={scannedAt ?? undefined}>{ago(scannedAt, now)}</time>
        </div>
      </div>

      <div className="d-score">
        <div className="sc-l">
          <span className="big">
            {score ?? '—'}
            <span className="dn">/100</span>
          </span>
          {dotTier && <DotStrip value={score ?? 0} tier={dotTier} className="d-dots" />}
        </div>
        <CapabilityStack tally={capabilityTally} />
      </div>

      <div className="d-find">
        {findings.total > 0 ? (
          <>
            {findings.critical > 0 && (
              <span className="sev cr">
                <i aria-hidden="true" />
                {findings.critical} critical
              </span>
            )}
            {findings.high > 0 && (
              <span className="sev hi">
                <i aria-hidden="true" />
                {findings.high} high
              </span>
            )}
            {findings.info > 0 && (
              <span className="sev in">
                <i aria-hidden="true" />
                {findings.info} info
              </span>
            )}
          </>
        ) : (
          <span className="none">
            <span className="ck" aria-hidden="true">
              ✓
            </span>{' '}
            No findings
          </span>
        )}
      </div>

      <div className="d-foot">
        <span className="d-rt">
          <RuntimeMonogram runtime={runtime} showName />
        </span>
      </div>
    </a>
  )
}
