import BandPill from '../atoms/BandPill'
import { flashToast } from '../atoms/Toast'

export interface FindingRowProps {
  ruleId: string
  severity: 'info' | 'low' | 'medium' | 'high' | 'critical'
  category: string
  /** Optional concise human description of the finding (not the rule id / path). */
  finding?: string
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

function lineLabel(start: number, end?: number | null): string {
  return end && end !== start ? `${start}–${end}` : `${start}`
}

/**
 * One finding rendered as a forensic evidence record inside a `SubScoreAccordion`
 * or the per-capability report. Two stacked rows that wrap (never a fixed grid,
 * so long paths can't spill): a head (severity · rule_id → methodology · category)
 * and an evidence line (file:line location · content-hash chip with copy · a
 * "View on GitHub" button). The rule_id links to the methodology; the GitHub
 * navigation lives behind a button, not raw path text.
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
  const lines = lineLabel(evidence.lineStart, evidence.lineEnd)
  const locFull = `${evidence.filePath}:${lines}`
  const sha = matchedContentSha256

  async function copySha() {
    if (!sha) return
    try {
      await navigator.clipboard.writeText(`sha256:${sha}`)
      flashToast('SHA-256 copied')
    } catch {
      flashToast('Copy failed — please copy manually')
    }
  }

  return (
    <li className="finding-row">
      <div className="fr-head">
        <span className="fr-sev">
          <BandPill tier={SEVERITY_TIER[severity]} label={severity.toUpperCase()} />
        </span>
        <a
          className="fr-rule"
          href={remediationLink}
          target="_blank"
          rel="noreferrer noopener"
          title="View this rule in the methodology"
        >
          <code>{ruleId}</code>
        </a>
        <span className="fr-cat">{category}</span>
      </div>

      {finding ? <p className="fr-desc">{finding}</p> : null}

      <div className="fr-evidence">
        <span className="fr-loc" title={locFull}>
          <FileGlyph />
          <span className="fr-loc-path">{evidence.filePath}</span>
          <span className="fr-loc-lines">:{lines}</span>
        </span>

        {sha ? (
          <span className="fr-sha">
            <code title={`sha256:${sha}`}>sha256:{sha.slice(0, 12)}…</code>
            <button type="button" className="fr-copy" onClick={copySha} aria-label="Copy SHA-256">
              <CopyGlyph />
            </button>
          </span>
        ) : null}

        {evidence.href ? (
          <a
            className="fr-gh"
            href={evidence.href}
            target="_blank"
            rel="noreferrer noopener"
            title={locFull}
          >
            <GitHubGlyph />
            <span>View on GitHub</span>
          </a>
        ) : null}
      </div>
    </li>
  )
}

const FileGlyph = () => (
  <svg
    width="13"
    height="13"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="1.7"
    strokeLinecap="square"
    strokeLinejoin="miter"
    aria-hidden="true"
  >
    <path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z" />
    <path d="M14 3v6h6" />
  </svg>
)

const CopyGlyph = () => (
  <svg
    width="13"
    height="13"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="1.7"
    strokeLinecap="square"
    strokeLinejoin="miter"
    aria-hidden="true"
  >
    <rect x="9" y="9" width="11" height="11" rx="0" />
    <path d="M5 15H4a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1h10a1 1 0 0 1 1 1v1" />
  </svg>
)

const GitHubGlyph = () => (
  <svg width="13" height="13" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">
    <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.01 8.01 0 0 0 16 8c0-4.42-3.58-8-8-8z" />
  </svg>
)
