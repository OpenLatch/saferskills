import SegmentedTabs, { panelId } from '@ui/components/atoms/SegmentedTabs'
import Toggle from '@ui/components/atoms/Toggle'
import DropZone from '@ui/components/molecules/DropZone'
import { useState } from 'react'
import { track } from '@/lib/analytics'
import type { ScanUploadResponse, Visibility } from '@/lib/api/scans'
import { useUploadFlow } from '@/lib/hooks/useUploadFlow'
import { SCAN_TABS, UPLOAD_ACCEPT, UPLOAD_MAX_BYTES } from '@/lib/upload'

type Tab = 'upload' | 'url'

/**
 * Homepage / 404 audit-panel affordance (D-UP-25). The Upload path now runs
 * **inline** (no /scan redirect, no IndexedDB handoff): pick files → the compact
 * DropZone collapses + shows progress → on success we navigate to the result.
 * The URL path still redirects to /scan?prefill=<url> (the full repo-scan
 * ceremony lives there). `homepage_scan_panel_started` fires on the first pick;
 * `homepage_scan_submitted` fires on the actual inline submit.
 */
export default function HomeScanPanel() {
  const [tab, setTab] = useState<Tab>('upload')
  const [visibility, setVisibility] = useState<Visibility>('public')
  const [urlValue, setUrlValue] = useState('')
  const [started, setStarted] = useState(false)

  const upload = useUploadFlow()

  function onFiles(files: File[]) {
    if (!started) {
      track('homepage_scan_panel_started', { artifact_source: 'upload', visibility })
      setStarted(true)
    }
    upload.onFiles(files)
  }

  function navigateToResult(res: ScanUploadResponse) {
    const dest = visibility === 'unlisted' && res.share_url ? res.share_url : `/scans/${res.id}`
    window.location.assign(dest)
  }

  function submitUpload() {
    if (upload.uploading || upload.files.length === 0) return
    track('homepage_scan_submitted', { artifact_source: 'upload', visibility })
    void upload.submit({ visibility, onResult: navigateToResult })
  }

  function goUrl() {
    track('homepage_scan_panel_started', { artifact_source: 'github', visibility })
    const q = new URLSearchParams()
    const v = urlValue.trim()
    if (v) q.set('prefill', v)
    if (visibility === 'unlisted') q.set('visibility', 'unlisted')
    const qs = q.toString()
    window.location.assign(`/scan${qs ? `?${qs}` : ''}`)
  }

  return (
    <div className="hs-panel">
      <SegmentedTabs
        variant="segmented"
        idBase="hs"
        ariaLabel="Scan mode"
        tabs={SCAN_TABS}
        value={tab}
        onChange={(id) => setTab(id as Tab)}
      />

      {tab === 'upload' ? (
        <div id={panelId('hs', 'upload')} role="tabpanel" aria-labelledby="hs-tab-upload">
          <DropZone
            compact
            onFilesSelected={onFiles}
            accept={[...UPLOAD_ACCEPT]}
            maxBytes={UPLOAD_MAX_BYTES}
            state={upload.dzState}
            progress={upload.progress}
            selectedFiles={upload.selectedFiles}
            error={upload.dzError ?? undefined}
            onRemove={upload.onRemove}
          />
          {upload.files.length > 0 && (
            <button
              type="button"
              className="hs-scan"
              disabled={upload.uploading}
              onClick={submitUpload}
            >
              {upload.uploading ? 'Scanning…' : 'Scan now'}{' '}
              <span className="kbd" aria-hidden="true">
                ↵
              </span>
            </button>
          )}
        </div>
      ) : (
        <div id={panelId('hs', 'url')} role="tabpanel" aria-labelledby="hs-tab-url">
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
                aria-label="Paste a GitHub URL to scan"
                value={urlValue}
                onChange={(e) => setUrlValue(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    e.preventDefault()
                    goUrl()
                  }
                }}
              />
            </label>
            <button
              type="button"
              className="p1-submit"
              aria-label="Continue to scan"
              onClick={goUrl}
            >
              <span className="p1-submit-ret" aria-hidden="true">
                ↵
              </span>
            </button>
          </div>
        </div>
      )}

      <div className="hs-vis">
        <Toggle
          compact
          checked={visibility === 'public'}
          onChange={(pub) => setVisibility(pub ? 'public' : 'unlisted')}
          label="Make results public"
          tone={tab === 'url' ? 'orange' : 'teal'}
          describedById="hs-vis-help"
        />
      </div>
      <p id="hs-vis-help" className="hs-vis-help">
        Private results are unlisted, link-only, and expire in 90 days.
      </p>
    </div>
  )
}
