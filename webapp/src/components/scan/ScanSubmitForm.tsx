import ScanInput from '@ui/components/molecules/ScanInput'
import { useState } from 'react'
import { track } from '@/lib/analytics'
import type { ScanReportSummary } from '@/lib/api/scans'
import { submitScan } from '@/lib/api/scans'

interface Props {
  recentScans?: ScanReportSummary[]
}

const VALID_URL = /^(https?:\/\/)?(www\.)?github\.com\/[^\s/]+\/[^\s/]+(\/.*)?\/?$/

export default function ScanSubmitForm({ recentScans = [] }: Props) {
  const [error, setError] = useState<string | null>(null)

  async function handleSubmit(githubUrl: string) {
    setError(null)
    if (!VALID_URL.test(githubUrl)) {
      setError('Paste a public github.com URL: `github.com/<org>/<repo>`')
      return
    }
    try {
      const response = await submitScan({ github_url: githubUrl })
      track('homepage_scan_submitted', { url_domain_class: 'github' })
      window.location.href = `/scans/${response.id}`
    } catch (e) {
      if (e instanceof Error && e.message === 'rate_limit_exceeded') {
        setError('10 scans/day per IP. Try again tomorrow or pin a previous scan.')
      } else if (e instanceof Error && e.message === 'invalid_url') {
        setError("The URL didn't resolve to a public GitHub repository.")
      } else {
        setError('Scan submission failed. Try again in a moment.')
      }
    }
  }

  return (
    <div className="scan-submit-form">
      <span className="eyebrow eyebrow-rule">SUBMIT · 01</span>
      <h2 className="scan-submit-form-title">Scan a public repository</h2>
      <ScanInput onSubmit={handleSubmit} error={error} />
      <p className="scan-submit-form-hint">
        Example: <code>github.com/openlatch/saferskills</code> · public repos only · re-scan
        cooldown 24h
      </p>
      {recentScans.length > 0 ? (
        <section className="scan-submit-form-recent" aria-label="Recent scans">
          <span className="eyebrow eyebrow-rule">RECENT SCANS · LAST 4</span>
          <ul className="scan-submit-form-recent-list">
            {recentScans.slice(0, 4).map((scan) => (
              <li key={scan.id}>
                <a href={`/scans/${scan.id}`}>
                  <strong>{scan.title ?? scan.slug}</strong>
                  <span className="scan-submit-form-recent-score">{scan.aggregate_score}/100</span>
                  <span className={`scan-submit-form-recent-tier tier-${scan.tier}`}>
                    {scan.tier}
                  </span>
                </a>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </div>
  )
}
