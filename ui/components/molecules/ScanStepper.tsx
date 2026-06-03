export type StepStatus = 'pending' | 'running' | 'completed' | 'failed'

export interface ScanStep {
  /** Stable key (e.g. "security"). */
  key: string
  /** "01" / "02" / … shown in the circle until completed. */
  index: string
  /** Display name (e.g. "Security"). */
  name: string
  /** Terse uppercase tag chip (e.g. "rules"). */
  tag?: string
  /** Plain-language explanation of what the stage does. */
  description?: string
  status: StepStatus
  /** Connector fill 0–100 (completed → 100, running → within-stage %, else 0). */
  fillPct?: number
  /** Within-stage % shown on the active step's "running…" meta. */
  runningPct?: number
}

interface Props {
  steps: ScanStep[]
  /** Header label (e.g. "Stages · 4"). */
  heading?: string
  /** Live current-stage label shown at the right of the header. */
  currentLabel?: string
}

function CheckGlyph() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" aria-hidden="true">
      <path d="M5 12.5 10 17.5 19 6.5" strokeLinecap="square" />
    </svg>
  )
}

/**
 * Vertical scan-stage stepper: a connector rail running through the centre of
 * each step circle, filling top-to-bottom as stages complete. Each step carries
 * a plain-language explanation so a non-expert understands what is being checked,
 * plus a live "running… N%" meta on the active step. CSS: `.scan-stepper` in
 * `ui/styles/components.css`. Replaces the old per-stage `ScanStageCard` tiles.
 */
export default function ScanStepper({ steps, heading = 'Stages', currentLabel }: Props) {
  return (
    <div className="scan-stepper">
      <div className="scan-stepper-head">
        <span>{heading}</span>
        {currentLabel ? <span className="scan-stepper-cur">{currentLabel}</span> : null}
      </div>
      <ol className="scan-stepper-list">
        {steps.map((step) => {
          const done = step.status === 'completed'
          return (
            <li
              key={step.key}
              className={`scan-step is-${step.status}`}
              aria-label={`${step.name} — ${step.status}`}
            >
              <span className="scan-step-rail" aria-hidden="true" />
              <span
                className="scan-step-fill"
                aria-hidden="true"
                style={{ height: `${Math.max(0, Math.min(100, step.fillPct ?? 0))}%` }}
              />
              <span className="scan-step-mark" aria-hidden="true">
                {done ? <CheckGlyph /> : <span>{step.index}</span>}
              </span>
              <div className="scan-step-body">
                <div className="scan-step-head">
                  <span className="scan-step-name">{step.name}</span>
                  {step.tag ? <span className="scan-step-tag">{step.tag}</span> : null}
                </div>
                {step.description ? <p className="scan-step-desc">{step.description}</p> : null}
                {step.status === 'running' ? (
                  <span className="scan-step-meta">
                    <span className="scan-step-spin" aria-hidden="true" />
                    <span>running… {Math.round(step.runningPct ?? 0)}%</span>
                  </span>
                ) : null}
              </div>
            </li>
          )
        })}
      </ol>
    </div>
  )
}
