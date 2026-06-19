export interface TranscriptLine {
  lineNo: number
  text: string
  /** The line that leaked the planted canary (highlighted). */
  hit: boolean
}

export interface RedactedTranscriptProps {
  /** Evidence file label, e.g. `transcript:AS-06`. */
  file: string
  lang?: string | null
  lines: TranscriptLine[]
  /** Confirmed-exfil flag — `leaked_canary_slot` set + verdict vulnerable. */
  exfil?: boolean
}

const LockGlyph = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" aria-hidden="true">
    <rect x="4" y="11" width="16" height="10" />
    <path d="M7.5 11V7.5a4.5 4.5 0 0 1 9 0V11" />
  </svg>
)

const FlagGlyph = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" aria-hidden="true">
    <path d="M12 3v13M12 21h.01M5 8l7-4 7 4v6l-7 4-7-4z" />
  </svg>
)

/**
 * Unlisted-route redacted transcript. The report
 * `evidence_excerpt` is a FLAT line-window `{file, lang, truncated, lines[]}` —
 * NOT role-tagged turns — so we render a verbatim line-window (reusing the `.ex`
 * gutter+code grammar inside the dark `.transcript` chrome) and highlight the
 * `hit:true` line as the leaked canary (`.canary`). A confirmed-exfil flag
 * (`.ts-flag`) closes the block.
 *
 * Defensive: returns `null` when there are no lines, so it is structurally
 * impossible to render on the public route (which carries `evidence_excerpt: null`).
 */
export default function RedactedTranscript({
  file,
  lang,
  lines,
  exfil = false,
}: RedactedTranscriptProps) {
  if (!lines || lines.length === 0) return null
  return (
    <div className="fc-evidence">
      <div className="fc-lbl">Redacted transcript</div>
      <div className="transcript">
        <div className="ts-meta">
          <span className="lock">
            <LockGlyph /> redacted
          </span>
          <span className="ts-file">{file}</span>
          {lang ? <span>· {lang}</span> : null}
        </div>
        <div className="ts-lines">
          {lines.map((l) => (
            <div className={`ex-line${l.hit ? ' canary' : ''}`} key={l.lineNo}>
              <span className="ln">{l.lineNo}</span>
              <span className="code">{l.text.length > 0 ? l.text : ' '}</span>
            </div>
          ))}
        </div>
        {exfil ? (
          <div className="ts-flag">
            <FlagGlyph />
            <span>
              <b>Confirmed exfiltration</b> — the planted canary appeared in recorded agent output.
            </span>
          </div>
        ) : null}
      </div>
    </div>
  )
}
