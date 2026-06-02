import SegmentedTabs, { panelId } from '@ui/components/atoms/SegmentedTabs'
import Toggle from '@ui/components/atoms/Toggle'
import DropZone, { type DropZoneState } from '@ui/components/molecules/DropZone'
import { useEffect, useState } from 'react'
import { track } from '@/lib/analytics'
import { submitScan, submitUpload, UploadError, type Visibility } from '@/lib/api/scans'
import {
  guessKind,
  precheckFile,
  SCAN_TABS,
  UPLOAD_ACCEPT,
  UPLOAD_MAX_BYTES,
  uploadErrorMessage,
} from '@/lib/upload'
import { takePendingUpload } from '@/lib/upload-handoff'

const VALID_URL = /^(https?:\/\/)?(www\.)?github\.com\/[^\s/]+\/[^\s/]+(\/.*)?\/?$/
const VALID_SLUG = /^[^\s/]+\/[^\s/]+$/

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
  const [busy, setBusy] = useState(false)

  // Upload state.
  const [file, setFile] = useState<File | null>(null)
  const [dzState, setDzState] = useState<DropZoneState>('idle')
  const [progress, setProgress] = useState(0)
  const [dzError, setDzError] = useState<{ code: string; message: string } | null>(null)

  // URL state.
  const [urlValue, setUrlValue] = useState('')
  const [urlError, setUrlError] = useState<string | null>(null)

  // Pick up a homepage handoff (a stashed File) or a ?prefill= GitHub URL.
  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    if (params.get('visibility') === 'unlisted') setVisibility('unlisted')
    const prefill = params.get('prefill')
    if (prefill) {
      setUrlValue(prefill)
      setTab('url')
    }
    const m = window.location.hash.match(/pending=([a-f0-9]+)/)
    if (!m) return
    history.replaceState(null, '', window.location.pathname + window.location.search)
    takePendingUpload(m[1]).then((pending) => {
      if (!pending) return
      setFile(pending.file)
      setVisibility(pending.visibility)
      setDzState('selected')
      setTab('upload')
    })
  }, [])

  function onFile(f: File) {
    const pre = precheckFile(f)
    if (!pre.ok) {
      setFile(null)
      setDzError({ code: pre.code, message: pre.message })
      setDzState('error')
      return
    }
    setFile(f)
    setDzError(null)
    setDzState('selected')
  }

  function onRemove() {
    setFile(null)
    setDzError(null)
    setDzState('idle')
  }

  function navigateToResult(res: { id: string; share_url?: string | null }) {
    const dest = visibility === 'unlisted' && res.share_url ? res.share_url : `/scans/${res.id}`
    navigateWithHandoff(dest, () => setHandoff(true))
  }

  async function submitUploadPath() {
    if (!file) {
      // onFile already pre-checks before setting `file`, so reaching here means no file.
      setDzError({ code: 'no_file', message: uploadErrorMessage('no_file') })
      setDzState('error')
      return
    }
    setBusy(true)
    setDzError(null)
    setProgress(0)
    setDzState('uploading')
    try {
      const res = await submitUpload(file, { visibility }, (loaded, total) =>
        setProgress(total ? loaded / total : 0)
      )
      setProgress(1)
      navigateToResult(res)
    } catch (e) {
      setBusy(false)
      if (e instanceof UploadError) {
        setDzError({ code: e.code, message: uploadErrorMessage(e.code, e.reason) })
      } else {
        setDzError({ code: 'upload_failed', message: uploadErrorMessage('upload_failed') })
      }
      setDzState('error')
    }
  }

  async function submitUrlPath() {
    setUrlError(null)
    const raw = urlValue.trim()
    const githubUrl = VALID_SLUG.test(raw) ? `https://github.com/${raw}` : raw
    if (!VALID_URL.test(githubUrl)) {
      setUrlError('Paste a public github.com URL: `github.com/<org>/<repo>`')
      return
    }
    setBusy(true)
    try {
      const res = await submitScan({ github_url: githubUrl, visibility })
      track('homepage_scan_submitted', { url_domain_class: 'github' })
      navigateToResult(res)
    } catch (e) {
      setBusy(false)
      if (e instanceof Error && e.message === 'rate_limit_exceeded') {
        setUrlError(uploadErrorMessage('rate_limit_exceeded'))
      } else if (e instanceof Error && e.message === 'invalid_url') {
        setUrlError("The URL didn't resolve to a public GitHub repository.")
      } else {
        setUrlError('Scan submission failed. Try again in a moment.')
      }
    }
  }

  function handleSubmit() {
    if (busy) return
    if (tab === 'upload') submitUploadPath()
    else submitUrlPath()
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
            onFileSelected={onFile}
            accept={[...UPLOAD_ACCEPT]}
            maxBytes={UPLOAD_MAX_BYTES}
            state={dzState}
            progress={progress}
            selectedFile={
              file ? { name: file.name, size: file.size, kind: guessKind(file) } : undefined
            }
            error={dzError ?? undefined}
            onRemove={onRemove}
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
            <div className={`p1-input${urlValue ? ' has-value' : ''}`}>
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
                  value={urlValue}
                  onChange={(e) => setUrlValue(e.target.value)}
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
          </div>
          <div className="hint">
            {urlError ? (
              <span role="alert" className="scan-error">
                {urlError}
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
        disabled={busy}
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
    </div>
  )
}
