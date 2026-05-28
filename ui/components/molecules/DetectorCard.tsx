interface Props {
  ruleId: string
  status: 'running' | 'completed' | 'queued' | 'skipped'
  filePath?: string
  elapsedMs?: number
}

const STATUS_LABEL = {
  running: 'Running',
  completed: 'OK',
  queued: 'Queued',
  skipped: 'Skipped',
} as const

/**
 * Per-detector card rendered inside the active stage on /scans/<id>.
 * Vocabulary: `mockups/hifi/app-pages.css::.detector-card`.
 */
export default function DetectorCard({ ruleId, status, filePath, elapsedMs }: Props) {
  return (
    <article className={`detector-card detector-card-${status}`} aria-label={`Detector ${ruleId} — ${STATUS_LABEL[status]}`}>
      <header className="detector-card-head">
        <code className="detector-card-rule">{ruleId}</code>
        <span className={`chip chip-${status}`}>
          {status === 'running' ? <span className="chip-dot pulse" aria-hidden="true" /> : null}
          {status === 'completed' ? <span className="chip-check" aria-hidden="true">✓</span> : null}
          {STATUS_LABEL[status]}
        </span>
      </header>
      {filePath ? <p className="detector-card-path">{filePath}</p> : null}
      {elapsedMs != null ? (
        <p className="detector-card-elapsed">
          {(elapsedMs / 1000).toFixed(2)}s
        </p>
      ) : null}
    </article>
  )
}
