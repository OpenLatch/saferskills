import { useEffect, useRef } from 'react'

/** Visual class of a terminal line — drives the leading glyph + color. */
export type TerminalKind = 'cmd' | 'run' | 'ok' | 'warn' | 'dim' | 'done'

/** Inline tone for a span inside a line (rule_id, file path, number, …). */
export type TerminalTone = 'cmd' | 'rule' | 'path' | 'num' | 'dim'

export interface TerminalSegment {
  text: string
  tone?: TerminalTone
}

export interface TerminalLine {
  /** Stable identity — keeps already-rendered lines from re-animating. */
  id: string
  kind: TerminalKind
  segments: TerminalSegment[]
}

interface Props {
  /** Ordered log lines; new lines stream in (animated on mount). */
  lines: TerminalLine[]
  /** Chrome title (centered). */
  title?: string
  /** Live stage label shown at the right of the chrome (e.g. "security"). */
  currentStage?: string
  /** Terminal reached its terminal state — stops the caret + live dot. */
  complete?: boolean
  /** Drops the caret + line-entrance motion for `prefers-reduced-motion`. */
  reducedMotion?: boolean
}

/** Leading glyph rendered by the component per line kind (kept out of data). */
const GLYPH: Record<TerminalKind, string> = {
  cmd: '$',
  run: '→',
  ok: '✓',
  warn: '⚠',
  dim: '',
  done: '✓',
}

/**
 * Streaming terminal readout in the homepage `iw-window` aesthetic (mac chrome,
 * Space Mono, scanlines), purpose-built for the in-progress scan page. Lines are
 * structured token segments (never raw HTML) so API-derived strings stay
 * `textContent` — no injection surface. Each new line animates in once; the
 * caret blinks on the last line until `complete`. CSS: `.scan-terminal` in
 * `ui/styles/components.css` (re-roots the `--t-*` ANSI palette onto itself).
 *
 * (Distinct from `webapp/.../scan/ScanConsole.tsx`, which is the scan-submit
 * entry flow — this is a read-only progress readout.)
 */
export default function ScanTerminal({
  lines,
  title = 'saferskills scan',
  currentStage,
  complete = false,
  reducedMotion = false,
}: Props) {
  const bodyRef = useRef<HTMLDivElement>(null)

  // Keep the newest line in view as the log grows.
  useEffect(() => {
    const el = bodyRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [lines.length])

  const lastIndex = lines.length - 1

  return (
    <div className={`scan-terminal${reducedMotion ? ' reduced-motion' : ''}`}>
      <div className="scan-terminal-chrome">
        <span className="mac-traffic" aria-hidden="true">
          <span className="l-r" />
          <span className="l-y" />
          <span className="l-g" />
        </span>
        <span className="scan-terminal-title">{title}</span>
        <span className="scan-terminal-live">
          {!complete ? <span className="scan-terminal-live-dot" aria-hidden="true" /> : null}
          <b>{complete ? 'complete' : (currentStage ?? 'starting')}</b>
        </span>
      </div>
      <div
        className="scan-terminal-body"
        ref={bodyRef}
        role="log"
        aria-live="polite"
        aria-label="Scan log"
      >
        {lines.map((line, i) => {
          const glyph = GLYPH[line.kind]
          const showCaret = !complete && !reducedMotion && i === lastIndex
          return (
            <div key={line.id} className={`scan-term-line tk-${line.kind}`}>
              {glyph ? (
                <span className="scan-term-glyph" aria-hidden="true">
                  {glyph}{' '}
                </span>
              ) : null}
              {line.segments.map((seg, j) => (
                <span key={`${line.id}-${j}`} className={seg.tone ? `tt-${seg.tone}` : undefined}>
                  {seg.text}
                </span>
              ))}
              {showCaret ? <span className="scan-term-caret" aria-hidden="true" /> : null}
            </div>
          )
        })}
      </div>
    </div>
  )
}
