export type StageStatus = 'pending' | 'running' | 'completed' | 'failed'

interface Props {
  /** "01" / "02" / ... */
  index: string
  /** Stage display name (e.g. "Fetch"). */
  name: string
  /** Short description rendered under the name. */
  description?: string
  /** Status pill chip on the right. */
  status: StageStatus
  /** Detectors completed for this stage. */
  detectorsDone?: number
  /** Total detectors for this stage. */
  detectorsTotal?: number
  /** Elapsed seconds in this stage, or estimate. */
  elapsedLabel?: string
}

const STATUS_LABEL: Record<StageStatus, string> = {
  pending: 'Queued',
  running: 'Running',
  completed: 'Done',
  failed: 'Failed',
}

/**
 * Per-stage card used on /scans/<id> (in-progress branch).
 * Vocabulary: `mockups/hifi/app-pages.css::.stage-card`. The active stage
 * (status=running) gets a teal-tint border + background per the design.
 */
export default function ScanStageCard({
  index,
  name,
  description,
  status,
  detectorsDone,
  detectorsTotal,
  elapsedLabel,
}: Props) {
  return (
    <article className={`stage-card stage-card-${status}`} aria-label={`Stage ${index}: ${name}`}>
      <header className="stage-card-head">
        <span className="stage-card-index">{index}</span>
        <span className={`chip chip-${status}`}>
          <span className={status === 'running' ? 'chip-dot pulse' : 'chip-dot'} aria-hidden="true" />
          {STATUS_LABEL[status]}
        </span>
      </header>
      <h3 className="stage-card-name">{name}</h3>
      {description ? <p className="stage-card-desc">{description}</p> : null}
      <footer className="stage-card-meta">
        {detectorsTotal != null ? (
          <span>
            <strong>{detectorsDone ?? 0}</strong>
            <span className="stage-card-slash"> / </span>
            {detectorsTotal}
            <span className="stage-card-unit"> detectors</span>
          </span>
        ) : null}
        {elapsedLabel ? <span className="stage-card-elapsed">{elapsedLabel}</span> : null}
      </footer>
    </article>
  )
}
