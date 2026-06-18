import { useState } from 'react'

import { flashToast } from '../atoms/Toast'

export interface RemediationSaferPattern {
  before: string
  after: string
}

export interface RemediationTerminalProps {
  /** The headline remediation action. */
  action: string
  /** Numbered steps; omitted/empty renders no list. */
  steps?: string[] | null
  /** Diff-colored before/after; null renders steps only (no terminal snippet). */
  saferPattern?: RemediationSaferPattern | null
  /** Terminal-chrome label (the `.who` slot). */
  filename?: string
  /** Text copied by the Copy button; defaults to the safer-pattern `after` line. */
  copyText?: string
}

const CopyGlyph = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" aria-hidden="true">
    <rect x="9" y="9" width="11" height="11" rx="1" />
    <path d="M5 15V5a1 1 0 0 1 1-1h10" />
  </svg>
)

/**
 * Per-finding terminal-chrome remediation: the action line +
 * numbered steps, then a diff-colored Avoid→Safer snippet inside a macOS terminal
 * (`.ar-term`) with a Copy → Copied button. Renders steps only when there is no
 * `saferPattern`. CSS (`.ar-rem-*` / `.ar-term` / `.at-*`) is DS-owned in
 * components.css; the snippet surface is part of the sanctioned terminal palette.
 */
export default function RemediationTerminal({
  action,
  steps,
  saferPattern = null,
  filename = 'remediation',
  copyText,
}: RemediationTerminalProps) {
  const [copied, setCopied] = useState(false)
  const text = copyText ?? saferPattern?.after ?? action

  async function onCopy() {
    try {
      await navigator.clipboard.writeText(text)
      setCopied(true)
      flashToast('Copied to clipboard')
      window.setTimeout(() => setCopied(false), 1400)
    } catch {
      flashToast('Copy failed — please copy manually')
    }
  }

  return (
    <div className="fc-fix ar-remediation">
      <div className="fc-lbl">How to fix</div>
      <p className="fc-action ar-rem-action">{action}</p>
      {steps && steps.length > 0 ? (
        <ol className="ar-rem-steps">
          {steps.map((s, i) => (
            // biome-ignore lint/suspicious/noArrayIndexKey: steps are an ordered immutable list
            <li key={i}>{s}</li>
          ))}
        </ol>
      ) : null}
      {saferPattern ? (
        <div className="ar-fix-snippet">
          <div className="ar-rem-exlbl">Avoid → Safer pattern</div>
          <div className="ar-term">
            <div className="at-head">
              <span className="lights" aria-hidden="true">
                <span />
                <span />
                <span />
              </span>
              <span className="who">{filename}</span>
              <button
                type="button"
                className={`copy-btn${copied ? ' copied' : ''}`}
                onClick={onCopy}
              >
                <CopyGlyph />
                {copied ? 'Copied' : 'Copy'}
              </button>
            </div>
            <div className="at-body">
              <span className="del">- {saferPattern.before}</span>
              {'\n'}
              <span className="add">+ {saferPattern.after}</span>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  )
}
