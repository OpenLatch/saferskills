import BandPill from '@ui/components/atoms/BandPill'
import { useState } from 'react'
import { track } from '@/lib/analytics'
import type { ScanReportSummary, ScanTier } from '@/lib/api/scans'
import { submitScan } from '@/lib/api/scans'

interface Props {
  recentScans?: ScanReportSummary[]
}

const VALID_URL = /^(https?:\/\/)?(www\.)?github\.com\/[^\s/]+\/[^\s/]+(\/.*)?\/?$/
const VALID_SLUG = /^[^\s/]+\/[^\s/]+$/

// Documented operational constants (not metrics) — the rate-limit + runtime
// budget contract surfaced on /scan. See PRD §6.2 / I-02 D-25.
const TRUST = [
  { lbl: 'Rate', val: '10', sub: 'scans / day / IP' },
  { lbl: 'Signed in', val: '50', sub: 'scans / day' },
  { lbl: 'Runtime', val: '30s', sub: 'AWS Lambda budget' },
  { lbl: 'Persistence', val: '90d', sub: 'URL lifetime' },
] as const

function relAge(iso: string): string {
  const secs = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000)
  if (secs < 3600) return `${Math.max(1, Math.round(secs / 60))}m ago`
  if (secs < 86400) return `${Math.round(secs / 3600)}h ago`
  return `${Math.round(secs / 86400)}d ago`
}

function tierBand(tier: ScanTier): 'green' | 'yellow' | 'orange' | 'red' | null {
  return tier === 'unscoped' ? null : tier
}

export default function ScanSubmitForm({ recentScans = [] }: Props) {
  const [value, setValue] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function handleSubmit() {
    setError(null)
    const raw = value.trim()
    const githubUrl = VALID_SLUG.test(raw) ? `https://github.com/${raw}` : raw
    if (!VALID_URL.test(githubUrl)) {
      setError('Paste a public github.com URL: `github.com/<org>/<repo>`')
      return
    }
    setBusy(true)
    try {
      const response = await submitScan({ github_url: githubUrl })
      track('homepage_scan_submitted', { url_domain_class: 'github' })
      window.location.href = `/scans/${response.id}`
    } catch (e) {
      setBusy(false)
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
    <>
      <div className="sub-eyebrow">Submit · 01</div>
      <h2>Scan a public repository</h2>

      <div className="scan-url-input">
        <span className="lead">
          <svg viewBox="0 0 16 16" aria-hidden="true">
            <path
              fillRule="evenodd"
              d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0 0 16 8c0-4.42-3.58-8-8-8z"
            />
          </svg>
          github.com/
        </span>
        <input
          type="text"
          placeholder="anthropic/claude-mcp"
          autoComplete="off"
          aria-label="GitHub repository to scan"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              e.preventDefault()
              handleSubmit()
            }
          }}
        />
        <button className="submit" type="button" disabled={busy} onClick={handleSubmit}>
          {busy ? 'Scanning…' : 'Scan now ↵'}
        </button>
      </div>
      <div className="hint">
        {error ? (
          <span role="alert" className="scan-error">
            {error}
          </span>
        ) : (
          <>
            Example: <b>github.com/openlatch/saferskills</b> · public repos only · re-scan cooldown
            24h
          </>
        )}
      </div>

      {recentScans.length > 0 ? (
        <div className="scan-recent">
          <div className="head">
            <span>— Recent scans · last {Math.min(4, recentScans.length)} —</span>
            <span>auto-refresh · 30s</span>
          </div>
          <div className="grid">
            {recentScans.slice(0, 4).map((scan) => {
              const band = tierBand(scan.tier)
              const orgRepo = scan.slug.replace('--', '/')
              return (
                <a className="rs-cell" key={scan.id} href={`/scans/${scan.id}`}>
                  <div className="top">
                    <span className="nm">{scan.title ?? orgRepo}</span>
                    {band ? <BandPill tier={band} /> : <span className="band-pill">Unscoped</span>}
                  </div>
                  <div className="top">
                    <span className="scn">{scan.aggregate_score}</span>
                    <span className="rs-time">{relAge(scan.scanned_at)}</span>
                  </div>
                  <div className="bot">
                    scn_{scan.id.slice(0, 8)}… · {orgRepo}
                  </div>
                </a>
              )
            })}
          </div>
        </div>
      ) : null}

      <div className="scan-trust">
        {TRUST.map((t) => (
          <div className="it" key={t.lbl}>
            <div className="lbl">{t.lbl}</div>
            <div className="val">{t.val}</div>
            <div className="sub">{t.sub}</div>
          </div>
        ))}
      </div>
    </>
  )
}
