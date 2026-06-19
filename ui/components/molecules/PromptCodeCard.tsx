import type { ClipboardEvent, ReactNode } from 'react'
import { highlightAgentPrompt } from '../../lib/highlight-prompt'

export type PromptCopyState = 'idle' | 'copied' | 'busy'

interface Props {
  /** Head-row file title (e.g. "SaferSkills Agent Scan Prompt"). */
  title: string
  /** Prompt text, one entry per displayed line ('' renders an empty line). */
  lines: string[]
  /**
   * Syntax-tint the body as the SaferSkills Agent-Scan prompt (placeholders,
   * URLs, HTTP verbs, headers, the privacy paragraph). Opt-in — plain text
   * otherwise. Restores the v3 mockup's `.tok-*` coloring (`highlight-prompt`).
   */
  tinted?: boolean
  /**
   * Controlled copy-button state — the parent owns every transition (mint,
   * clipboard write, reset timer). 'busy' disables the control and shows a
   * pending label; 'copied' flips it to the brand-filled confirmation.
   */
  copyState: PromptCopyState
  /** Fired on Copy click. Side effects (fetch/Turnstile/clipboard) live in the parent. */
  onCopy: () => void
  /**
   * When true, a native `copy`/`cut` over the body text is intercepted:
   * `preventDefault()` stops the raw (un-minted) text reaching the clipboard and
   * `onCopy` is fired instead — so a manual select-then-copy routes through the
   * same mint flow as the Copy button (never copies `{{…}}` placeholders). Pass
   * it only while the body shows the pre-mint template; once the real prompt is
   * displayed, leave it off so native selection-copy of the live text works.
   */
  interceptCopy?: boolean
  /** Optional foot area under the code body (e.g. a visibility note). */
  footSlot?: ReactNode
}

const COPY_LABEL: Record<PromptCopyState, string> = {
  idle: 'Copy',
  busy: 'Copying…',
  copied: 'Copied',
}

const LIVE_MSG: Record<PromptCopyState, string> = {
  idle: '',
  busy: 'Copying the prompt…',
  copied: 'Prompt copied to clipboard',
}

const FileGlyph = () => (
  <svg viewBox="0 0 24 24" aria-hidden="true">
    <path d="M14 3v5h5" />
    <path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
  </svg>
)

const CopyGlyph = () => (
  <svg viewBox="0 0 24 24" aria-hidden="true">
    <rect x="8" y="8" width="13" height="13" rx="2" />
    <path d="M5 16V5a2 2 0 0 1 2-2h11" />
  </svg>
)

const CheckGlyph = () => (
  <svg viewBox="0 0 24 24" aria-hidden="true">
    <path d="M5 12.5 10 17.5 19 6.5" />
  </svg>
)

/**
 * Code-editor-chrome prompt block — head row with a file
 * glyph + title + Copy button; body of line-numbered mono text on a code-editor
 * surface (dark in dark mode, a light editor skin in light mode — see the
 * `.pc-*` light skin in components.css). Shared by the homepage "Scan a Running
 * Agent" card and the activation island.
 *
 * Fully presentational: `copyState` is a controlled prop and `onCopy` is a
 * plain callback — NO fetch / Turnstile / clipboard logic in here. The
 * Copy→Copied flip is announced via a visually-hidden `role="status"` live
 * region (the DropZone/TurnstileGate house pattern). Line numbers are an
 * `aria-hidden`, non-selectable gutter so the prompt text selects/copies as
 * one block; rows are plain grid rows (no per-line measurement), so 30–80
 * lines render without layout jank.
 *
 * CSS: `.prompt-card`/`.pc-*` in `ui/styles/components.css` — own class
 * names, never the page-CSS `.code-editor`/`.ce-*`, so Ladle renders it
 * without page CSS.
 */
export default function PromptCodeCard({
  title,
  lines,
  copyState,
  onCopy,
  interceptCopy = false,
  footSlot,
  tinted = false,
}: Props) {
  const copyClass = `pc-copy${copyState === 'copied' ? ' is-copied' : ''}${
    copyState === 'busy' ? ' is-busy' : ''
  }`
  // Tint once per render — aligned 1:1 with `lines` so the row map can index it.
  const tintedLines = tinted ? highlightAgentPrompt(lines) : null
  // A manual copy/cut of the pre-mint template is hijacked into the same mint
  // path as the Copy button, so the raw `{{…}}` text never reaches the clipboard.
  // The hook owns re-entrancy (busy/gating/minting) — this just forwards intent.
  const onBodyClipboard = interceptCopy
    ? (e: ClipboardEvent<HTMLDivElement>) => {
        e.preventDefault()
        onCopy()
      }
    : undefined
  return (
    <div className="prompt-card">
      <div className="pc-head">
        <span className="pc-name">
          <FileGlyph />
          {title}
        </span>
        <button
          type="button"
          className={copyClass}
          onClick={onCopy}
          disabled={copyState === 'busy'}
          aria-busy={copyState === 'busy'}
        >
          {copyState === 'copied' ? <CheckGlyph /> : <CopyGlyph />}
          <span className="pc-lbl">{COPY_LABEL[copyState]}</span>
        </button>
      </div>
      {/* tabIndex makes the scrollable body keyboard-reachable (arrow-scroll) —
          axe `scrollable-region-focusable` (WCAG 2 A/AA); role+label name it.
          When `interceptCopy`, a manual copy/cut routes through the mint flow. */}
      <div
        className="pc-body"
        tabIndex={0}
        role="group"
        aria-label={title}
        onCopy={onBodyClipboard}
        onCut={onBodyClipboard}
      >
        {lines.map((line, i) => (
          // biome-ignore lint/suspicious/noArrayIndexKey: lines are a static positional list
          <div className="pc-line" key={i}>
            <span className="pc-ln" aria-hidden="true">
              {i + 1}
            </span>
            <span className="pc-lc">{tintedLines ? tintedLines[i] : line}</span>
          </div>
        ))}
      </div>
      {footSlot != null && <div className="pc-foot">{footSlot}</div>}
      <span className="sr-only" role="status" aria-live="polite">
        {LIVE_MSG[copyState]}
      </span>
    </div>
  )
}
