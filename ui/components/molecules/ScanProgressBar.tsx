interface Props {
  /** 0–100 inclusive. */
  completionPct: number
  /** Optional name of the currently running detector. */
  currentDetector?: string
  /** Elapsed ms for the current detector (driven by SSE payloads). */
  currentDetectorElapsedMs?: number
  /** "9 / 14 detectors complete" or similar. */
  progressLabel?: string
  /** Disables shimmer + transitions for `prefers-reduced-motion`. */
  reducedMotion?: boolean
}

/**
 * Wide horizontal scan-progress bar with shimmer animation (`mockups/hifi/app-pages.css::.progress-bar`).
 * The shimmer keyframe lives in page-scan-progress.css; the bar is purely
 * presentational here. Reduced-motion fallback: solid fill, no shimmer.
 */
export default function ScanProgressBar({
  completionPct,
  currentDetector,
  currentDetectorElapsedMs,
  progressLabel,
  reducedMotion,
}: Props) {
  const pct = Math.max(0, Math.min(100, Math.round(completionPct)))
  const elapsedLabel =
    currentDetector && currentDetectorElapsedMs != null
      ? `${currentDetector} running ${(currentDetectorElapsedMs / 1000).toFixed(1)}s`
      : currentDetector
  return (
    <div
      className={`progress-bar${reducedMotion ? ' reduced-motion' : ''}`}
      role="progressbar"
      aria-valuenow={pct}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-label={progressLabel ?? 'Scan progress'}
    >
      <div className="progress-bar-track">
        <div className="progress-bar-fill" style={{ width: `${pct}%` }}>
          <span className="progress-bar-shimmer" aria-hidden="true" />
        </div>
      </div>
      <div className="progress-bar-meta">
        {progressLabel ? <span className="progress-bar-label">{progressLabel}</span> : null}
        {elapsedLabel ? <span className="progress-bar-detector">{elapsedLabel}</span> : null}
        <span className="progress-bar-pct">{pct}%</span>
      </div>
    </div>
  )
}
