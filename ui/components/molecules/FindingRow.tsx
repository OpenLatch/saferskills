import BandPill from '../atoms/BandPill'

export interface FindingRowProps {
  ruleId: string
  severity: 'info' | 'low' | 'medium' | 'high' | 'critical'
  category: string
  finding: string
  matchedContentSha256?: string
  evidence: {
    filePath: string
    lineStart: number
    lineEnd?: number | null
    /** GitHub URL like `github.com/<org>/<repo>/blob/<sha>/<path>#L<line>`. */
    href?: string
  }
  remediationLink: string
}

// BandPill's tier is 4-band — `info` severity maps to `green` as the
// least-impactful neutral; the actual severity label is rendered on the pill
// itself, so the band color is purely decorative.
const SEVERITY_TIER: Record<FindingRowProps['severity'], 'green' | 'yellow' | 'orange' | 'red'> = {
  info: 'green',
  low: 'green',
  medium: 'yellow',
  high: 'orange',
  critical: 'red',
}

/**
 * Single-row finding entry rendered inside a `SubScoreAccordion`.
 * Columns: severity / rule_id / category / finding / evidence.
 */
export default function FindingRow({
  ruleId,
  severity,
  category,
  finding,
  matchedContentSha256,
  evidence,
  remediationLink,
}: FindingRowProps) {
  return (
    <li className="finding-row">
      <span className="finding-row-severity">
        <BandPill tier={SEVERITY_TIER[severity]} label={severity.toUpperCase()} />
      </span>
      <a className="finding-row-rule" href={remediationLink} target="_blank" rel="noreferrer noopener">
        <code>{ruleId}</code>
      </a>
      <span className="finding-row-category">{category}</span>
      <span className="finding-row-finding">
        <span>{finding}</span>
        {matchedContentSha256 ? (
          <code className="finding-row-hash" aria-label="Matched content SHA-256">
            sha256:{matchedContentSha256.slice(0, 12)}…
          </code>
        ) : null}
      </span>
      <span className="finding-row-evidence">
        {evidence.href ? (
          <a href={evidence.href} target="_blank" rel="noreferrer noopener">
            <code>
              {evidence.filePath}:{evidence.lineStart}
              {evidence.lineEnd && evidence.lineEnd !== evidence.lineStart ? `-${evidence.lineEnd}` : ''}
            </code>
          </a>
        ) : (
          <code>
            {evidence.filePath}:{evidence.lineStart}
          </code>
        )}
      </span>
    </li>
  )
}
