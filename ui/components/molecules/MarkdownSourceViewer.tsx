import { type ReactNode, useState } from 'react'

interface Props {
  /** File path shown in the chrome bar (e.g. `SKILL.md`). */
  path: string
  /** Raw byte size; rendered as `KB · Markdown`. */
  bytes: number
  /** Raw file body — shown in the Raw tab and copied by the copy button. */
  content: string
  /**
   * Pre-rendered markdown as React nodes. The caller renders it (the
   * `renderMarkdown` helper lives in `webapp/`); `ui/` must not import a
   * markdown renderer — that would invert the one-way dependency.
   */
  renderedHtml: ReactNode
}

/**
 * macOS-window-chrome markdown source viewer shared by the item-detail report
 * (`ItemTabs`) and the single-capability upload report (`CapabilityReportTabs`).
 *
 * Owns the Rendered/Raw toggle + the transient copy-confirmation state. The
 * rendered view is passed in as `renderedHtml` (a `ReactNode`) so the molecule
 * stays renderer-agnostic. CSS (`.md-*`) is DS-owned in
 * `ui/styles/components.css`.
 */
export default function MarkdownSourceViewer({ path, bytes, content, renderedHtml }: Props) {
  const [raw, setRaw] = useState(false)
  const [copied, setCopied] = useState(false)

  return (
    <div className="md-viewer">
      <div className="md-bar">
        <span className="md-dot r" />
        <span className="md-dot y" />
        <span className="md-dot g" />
        <span className="md-file">{path}</span>
        <span className="md-bytes">{(bytes / 1024).toFixed(1)} KB · Markdown</span>
        <div className="md-tools">
          <button type="button" className={`md-tab${raw ? '' : ' on'}`} onClick={() => setRaw(false)}>
            Rendered
          </button>
          <button type="button" className={`md-tab${raw ? ' on' : ''}`} onClick={() => setRaw(true)}>
            Raw
          </button>
          <button
            type="button"
            className="md-copy"
            onClick={() => {
              navigator.clipboard?.writeText(content)
              setCopied(true)
              setTimeout(() => setCopied(false), 1500)
            }}
          >
            {copied ? '✓ Copied' : '⧉ Copy'}
          </button>
        </div>
      </div>
      {raw ? <pre className="md-raw">{content}</pre> : <div className="md-body">{renderedHtml}</div>}
    </div>
  )
}
