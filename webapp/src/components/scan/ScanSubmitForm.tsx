import { useRef, useState } from 'react'
import { track } from '@/lib/analytics'
import { submitScan } from '@/lib/api/scans'

const VALID_URL = /^(https?:\/\/)?(www\.)?github\.com\/[^\s/]+\/[^\s/]+(\/.*)?\/?$/
const VALID_SLUG = /^[^\s/]+\/[^\s/]+$/

// Documented operational constants (not metrics) — the per-scan time budget +
// rate-limit + retention contract surfaced on /scan. See PRD §6.2 / I-02 D-25.
const LIMITS = [
  { lbl: 'Runtime', val: '30s', sub: 'per-scan budget' },
  { lbl: 'Rate', val: '10', sub: 'scans / day / IP' },
  { lbl: 'Signed in', val: '50', sub: 'scans / day' },
  { lbl: 'Persistence', val: '90d', sub: 'URL lifetime' },
] as const

export default function ScanSubmitForm() {
  const [value, setValue] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

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

      {/* Reuses the homepage "Audit" vocabulary — the orange `.p1-input` bar +
          the animated `.p1-progress` pipeline (both DS-owned in components.css),
          wired here to a real scan submission. */}
      <div className="scan-console audit">
        <div className={`p1-input${value ? ' has-value' : ''}`}>
          <span className="p1-icon" aria-hidden="true">
            <svg viewBox="0 0 24 24" focusable="false">
              <title>Scan</title>
              <path d="M10 13a5 5 0 0 0 7.07 0l3-3a5 5 0 1 0-7.07-7.07l-1.5 1.5" />
              <path d="M14 11a5 5 0 0 0-7.07 0l-3 3a5 5 0 1 0 7.07 7.07l1.5-1.5" />
            </svg>
          </span>
          <label className="p1-field">
            <span className="caret" aria-hidden="true" />
            <input
              ref={inputRef}
              type="text"
              placeholder="github.com/anthropic/claude-mcp"
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
          </label>
          <button
            type="button"
            className="p1-submit"
            aria-label="Scan repository"
            disabled={busy}
            onClick={handleSubmit}
          >
            <span className="p1-submit-ret" aria-hidden="true">
              {busy ? '…' : '↵'}
            </span>
          </button>
        </div>

        <div className="p1-progress" aria-hidden="true">
          <div className="row">
            <span>Audit pipeline</span>
            <span>
              <b>4</b> deterministic stages
            </span>
          </div>
          <div className="bar" />
          <div className="steps">
            <span className="ok">Fetch</span>
            <span className="ok">Lint</span>
            <span className="cur">Score</span>
            <span className="pen">Sign</span>
          </div>
        </div>
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

      <div className="scan-budget">
        <div className="scan-budget-head">
          <span className="t">Budget &amp; limits</span>
          <span className="n">no account needed</span>
        </div>
        <div className="scan-budget-grid">
          {LIMITS.map((t) => (
            <div className="budget-cell" key={t.lbl}>
              <div className="lbl">{t.lbl}</div>
              <div className="val">{t.val}</div>
              <div className="sub">{t.sub}</div>
            </div>
          ))}
        </div>
      </div>
    </>
  )
}
