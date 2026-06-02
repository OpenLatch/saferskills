import SegmentedTabs, { panelId } from '@ui/components/atoms/SegmentedTabs'
import Toast, { flashToast } from '@ui/components/atoms/Toast'
import Toggle from '@ui/components/atoms/Toggle'
import DropZone from '@ui/components/molecules/DropZone'
import { useEffect, useState } from 'react'
import { track } from '@/lib/analytics'
import type { Visibility } from '@/lib/api/scans'
import { useRepoScanFlow } from '@/lib/hooks/useRepoScanFlow'
import { useUploadFlow } from '@/lib/hooks/useUploadFlow'
import { SCAN_TABS, UPLOAD_ACCEPT, UPLOAD_HINT, UPLOAD_MAX_BYTES } from '@/lib/upload'

const VIS_EXPLAINER =
  'Public: listed in the catalog, permanent. Private: unlisted — only people with the link can see it, expires in 90 days.'
const PRIVATE_NOTE =
  "We'll give you a private (unlisted) link — anyone with the link can see it. It's not access-controlled."

type Tab = 'upload' | 'url'

function navigateWithHandoff(dest: string, onFade: () => void) {
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
    window.location.assign(dest)
    return
  }
  onFade()
  window.setTimeout(() => window.location.assign(dest), 200)
}

/**
 * Dual-mode submit console for /scan (D-UP-24). One island owns the tab +
 * visibility so the shared Toggle (teal/orange by mode) and the "Scan now"
 * button drive both the Upload (DropZone → POST /scans/upload) and Scan-repo
 * (GitHub URL → POST /scans) paths, with the D-UP-ANIM upload state machine.
 */
export default function ScanConsole() {
  const [tab, setTab] = useState<Tab>('upload')
  const [visibility, setVisibility] = useState<Visibility>('public')
  const [handoff, setHandoff] = useState(false)

  // Shared one-source-of-truth flows (also used on the homepage panel).
  const upload = useUploadFlow()
  const repo = useRepoScanFlow()

  // Pick up a ?prefill= GitHub URL (+ ?visibility= / ?deleted=). The homepage
  // upload + repo paths now run inline there — there is no File handoff anymore.
  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    // Landed here after deleting an unlisted report (D-UP-26) — confirm + clean the URL.
    if (params.get('deleted')) {
      flashToast('Report deleted')
      params.delete('deleted')
      const qs = params.toString()
      history.replaceState(null, '', window.location.pathname + (qs ? `?${qs}` : ''))
    }
    if (params.get('visibility') === 'unlisted') setVisibility('unlisted')
    const prefill = params.get('prefill')
    if (prefill) {
      repo.setUrlValue(prefill)
      setTab('url')
    }
  }, [repo.setUrlValue])

  function navigateToResult(res: { id: string; share_url?: string | null }) {
    const dest = visibility === 'unlisted' && res.share_url ? res.share_url : `/scans/${res.id}`
    navigateWithHandoff(dest, () => setHandoff(true))
  }

  const inFlight = repo.submitting || upload.uploading

  function handleSubmit() {
    if (inFlight) return
    // FE intent signal (closed-enum only — no URL/filename/bytes/token). The
    // backend emits the authoritative `scan_submitted` on the server side.
    track('homepage_scan_submitted', {
      artifact_source: tab === 'upload' ? 'upload' : 'github',
      visibility,
    })
    if (tab === 'upload') void upload.submit({ visibility, onResult: navigateToResult })
    else void repo.submit({ visibility, onResult: navigateToResult })
  }

  return (
    <div className={`scan-console-shell${handoff ? ' is-handoff' : ''}`}>
      <div className="sub-eyebrow">Submit · 01</div>
      <h2>Run an audit</h2>

      <SegmentedTabs
        variant="segmented"
        idBase="scan"
        ariaLabel="Scan mode"
        tabs={SCAN_TABS}
        value={tab}
        onChange={(id) => setTab(id as Tab)}
      />

      {tab === 'upload' ? (
        <div
          id={panelId('scan', 'upload')}
          role="tabpanel"
          aria-labelledby="scan-tab-upload"
          className="scan-pane"
        >
          <DropZone
            onFilesSelected={upload.onFiles}
            accept={[...UPLOAD_ACCEPT]}
            maxBytes={UPLOAD_MAX_BYTES}
            hint={UPLOAD_HINT}
            state={upload.dzState}
            progress={upload.progress}
            selectedFiles={upload.selectedFiles}
            error={upload.dzError ?? undefined}
            onRemove={upload.onRemove}
          />
        </div>
      ) : (
        <div
          id={panelId('scan', 'url')}
          role="tabpanel"
          aria-labelledby="scan-tab-url"
          className="scan-pane"
        >
          <div className="scan-console audit">
            <div className={`p1-input${repo.urlValue ? ' has-value' : ''}`}>
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
                  type="text"
                  placeholder="github.com/anthropic/claude-mcp"
                  autoComplete="off"
                  aria-label="GitHub repository to scan"
                  value={repo.urlValue}
                  onChange={(e) => repo.setUrlValue(e.target.value)}
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
                disabled={inFlight}
                onClick={handleSubmit}
              >
                <span className="p1-submit-ret" aria-hidden="true">
                  {inFlight ? '…' : '↵'}
                </span>
              </button>
            </div>
          </div>
          <div className="hint">
            {repo.urlError ? (
              <span role="alert" className="scan-error">
                {repo.urlError}
              </span>
            ) : (
              <>
                Example: <b>github.com/openlatch/saferskills</b> · public repos only · re-scan
                cooldown 24h
              </>
            )}
          </div>
        </div>
      )}

      <div className="scan-privacy">
        <div className="pv-row">
          <Toggle
            checked={visibility === 'public'}
            onChange={(pub) => setVisibility(pub ? 'public' : 'unlisted')}
            label="Make results public"
            tone={tab === 'url' ? 'orange' : 'teal'}
          />
          <span className="pv-info">
            <button type="button" className="pv-info-btn" aria-label={VIS_EXPLAINER}>
              <svg viewBox="0 0 16 16" aria-hidden="true" focusable="false">
                <circle cx="8" cy="8" r="7" />
                <path d="M8 7.2v4M8 4.6h.01" />
              </svg>
            </button>
            <span className="pv-tip" aria-hidden="true">
              {VIS_EXPLAINER}
            </span>
          </span>
        </div>
        {visibility === 'unlisted' && <p className="pv-note">{PRIVATE_NOTE}</p>}
      </div>

      <button
        type="button"
        className="scan-go"
        data-mode={tab}
        disabled={inFlight}
        onClick={handleSubmit}
      >
        Scan now{' '}
        <span className="kbd" aria-hidden="true">
          ↵
        </span>
      </button>

      <p className="scan-consent">
        By scanning you confirm you can share this content. Public results are published
        permanently. <a href="/privacy">See Privacy</a>.
      </p>

      <Toast />
    </div>
  )
}
