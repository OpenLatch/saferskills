import SegmentedTabs, { panelId } from '@ui/components/atoms/SegmentedTabs'
import Toggle from '@ui/components/atoms/Toggle'
import DropZone, { type DropZoneState } from '@ui/components/molecules/DropZone'
import { useState } from 'react'
import type { Visibility } from '@/lib/api/scans'
import { precheckFile, SCAN_TABS, UPLOAD_ACCEPT, UPLOAD_MAX_BYTES } from '@/lib/upload'
import { stashPendingUpload } from '@/lib/upload-handoff'

type Tab = 'upload' | 'url'

/**
 * Homepage audit-panel affordance (D-UP-25). It does NOT submit inline — on a
 * file drop it stashes the File (IndexedDB) and navigates to /scan#pending=<nonce>;
 * on a URL it navigates to /scan?prefill=<url>. The full submit ceremony lives on
 * /scan, where the user confirms (P1-5 — never auto-submit on arrival).
 */
export default function HomeScanPanel() {
  const [tab, setTab] = useState<Tab>('upload')
  const [visibility, setVisibility] = useState<Visibility>('public')
  const [dzState, setDzState] = useState<DropZoneState>('idle')
  const [dzError, setDzError] = useState<{ code: string; message: string } | null>(null)
  const [urlValue, setUrlValue] = useState('')

  async function onFile(f: File) {
    const pre = precheckFile(f)
    if (!pre.ok) {
      setDzError({ code: pre.code, message: pre.message })
      setDzState('error')
      return
    }
    setDzError(null)
    try {
      const nonce = await stashPendingUpload(f, visibility)
      window.location.assign(`/scan#pending=${nonce}`)
    } catch {
      window.location.assign('/scan')
    }
  }

  function goUrl() {
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
            onFileSelected={onFile}
            accept={[...UPLOAD_ACCEPT]}
            maxBytes={UPLOAD_MAX_BYTES}
            state={dzState}
            error={dzError ?? undefined}
          />
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
