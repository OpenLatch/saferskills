import Toast, { flashToast } from '@ui/components/atoms/Toast'
import Toggle from '@ui/components/atoms/Toggle'
import DropZone from '@ui/components/molecules/DropZone'
import TurnstileGate from '@ui/components/molecules/TurnstileGate'
import { useEffect, useState } from 'react'
import { PRIVATE_NOTE, VIS_EXPLAINER } from '@/components/scan/scan-privacy'
import { track } from '@/lib/analytics'
import type { Visibility } from '@/lib/api/scans'
import { useCaptchaGate } from '@/lib/hooks/useCaptchaGate'
import { useRepoScanFlow } from '@/lib/hooks/useRepoScanFlow'
import { useUploadFlow } from '@/lib/hooks/useUploadFlow'
import { UPLOAD_ACCEPT, UPLOAD_HINT, UPLOAD_MAX_BYTES } from '@/lib/upload'

type Action = 'upload' | 'url'

function navigateWithHandoff(dest: string, onFade: () => void) {
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
    window.location.assign(dest)
    return
  }
  onFade()
  window.setTimeout(() => window.location.assign(dest), 200)
}

/**
 * Capability submit console for /scan (D-UP-24, v3 single-pane restyle).
 * One pane carries BOTH inputs — DropZone, the "or paste a URL" divider, and
 * the GitHub URL field — plus the shared visibility Toggle and one
 * "Scan capability" submit that dispatches upload-vs-repo on whether files
 * are selected. Submit/validation/SSE logic is the untouched I-3.5 pair
 * (`useUploadFlow` / `useRepoScanFlow`) behind the same Turnstile gate.
 */
export default function ScanConsole() {
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
    if (prefill) repo.setUrlValue(prefill)
  }, [repo.setUrlValue])

  // Human-verification gate (Cloudflare Turnstile) — shared state machine. When a
  // site key is set, submit opens the modal and the real POST fires on `onVerified`;
  // unconfigured (dev) submits directly.
  const gate = useCaptchaGate()

  function navigateToResult(res: { id: string; share_url?: string | null }) {
    const dest = visibility === 'unlisted' && res.share_url ? res.share_url : `/scans/${res.id}`
    navigateWithHandoff(dest, () => setHandoff(true))
  }

  const inFlight = repo.submitting || upload.uploading
  // One submit, two paths: selected files win; otherwise the URL field
  // (whose own validation reports an empty/invalid value).
  const action: Action = upload.selectedFiles.length > 0 ? 'upload' : 'url'

  function run(act: Action, captchaToken?: string) {
    // FE intent signal (closed-enum only — no URL/filename/bytes/token). The
    // backend emits the authoritative `scan_submitted` on the server side.
    track('homepage_scan_submitted', {
      artifact_source: act === 'upload' ? 'upload' : 'github',
      visibility,
    })
    if (act === 'upload')
      void upload.submit({
        visibility,
        captchaToken,
        onResult: navigateToResult,
        onCaptchaRetry: () => gate.reopen('upload'),
      })
    else
      void repo.submit({
        visibility,
        captchaToken,
        onResult: navigateToResult,
        onCaptchaRetry: () => gate.reopen('url'),
      })
  }

  function handleSubmit(forced?: Action) {
    if (inFlight) return
    // The URL field's own submit affordances force the url path — with files
    // picked AND a URL typed, the old tabs let the user choose; the URL-side
    // Enter/↵ keeps that choice without removing the files.
    const act = forced ?? action
    if (!gate.request(act)) run(act)
  }

  function onVerified(token: string) {
    const act = gate.resolve()
    if (act) run(act, token)
  }

  return (
    <div className={`scan-console-shell${handoff ? ' is-handoff' : ''}`}>
      <div className="scan-pane">
        <DropZone
          onFilesSelected={upload.onFiles}
          accept={[...UPLOAD_ACCEPT]}
          maxBytes={UPLOAD_MAX_BYTES}
          hint={UPLOAD_HINT}
          dropCopy="Drag a SKILL.md or .zip here"
          state={upload.dzState}
          progress={upload.progress}
          selectedFiles={upload.selectedFiles}
          error={upload.dzError ?? undefined}
          onRemove={upload.onRemove}
        />

        <div className="cap-or">
          <span>or paste a URL</span>
        </div>

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
                placeholder="github.com/acme/linear-mcp or drop a SKILL.md"
                autoComplete="off"
                aria-label="GitHub repository to scan"
                value={repo.urlValue}
                onChange={(e) => repo.setUrlValue(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    e.preventDefault()
                    handleSubmit('url')
                  }
                }}
              />
            </label>
            <button
              type="button"
              className="p1-submit"
              aria-label="Scan repository"
              disabled={inFlight}
              onClick={() => handleSubmit('url')}
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

      <div className="scan-privacy">
        <div className="pv-row">
          <Toggle
            checked={visibility === 'public'}
            onChange={(pub) => setVisibility(pub ? 'public' : 'unlisted')}
            label="Make results public"
            tone="teal"
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

      <button type="button" className="scan-go" disabled={inFlight} onClick={() => handleSubmit()}>
        Scan capability{' '}
        <span className="kbd" aria-hidden="true">
          ↵
        </span>
      </button>

      <p className="scan-consent">
        By scanning you confirm you can share this content. Public results are published
        permanently. <a href="/privacy">See Privacy</a>.
      </p>

      {gate.siteKey && (
        <TurnstileGate
          open={gate.gateOpen}
          siteKey={gate.siteKey}
          onVerified={onVerified}
          onCancel={gate.cancel}
        />
      )}

      <Toast />
    </div>
  )
}
