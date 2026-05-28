import DetectorCard from '@ui/components/molecules/DetectorCard'
import ScanProgressBar from '@ui/components/molecules/ScanProgressBar'
import ScanStageCard, { type StageStatus } from '@ui/components/molecules/ScanStageCard'
import { useEffect, useMemo } from 'react'

import { useScanProgress } from '@/lib/hooks/useScanProgress'

interface Props {
  scanId: string
  /** Initial target — rendered before the SSE channel opens. */
  target?: string
  /** Used for the elapsed-time KPI tile. */
  startedAt?: string
}

const VISIBLE_STAGES = [
  { index: '01', name: 'Fetch', key: 'fetch', description: 'Resolve repo + walk files.' },
  {
    index: '02',
    name: 'Security',
    key: 'security',
    description: 'Prompt-injection + RCE + secret-exfil rules.',
  },
  {
    index: '03',
    name: 'Supply chain',
    key: 'supply_chain',
    description: 'Typosquats, drift, unsigned bundles.',
  },
  {
    index: '04',
    name: 'Score & sign',
    key: 'sign',
    description: 'Aggregate, critical-floor, sign report.',
  },
] as const

function _stageStatus(status: 'pending' | 'running' | 'completed' | 'failed'): StageStatus {
  return status
}

export default function ScanProgressBoard({ scanId, target, startedAt }: Props) {
  const state = useScanProgress(scanId)

  useEffect(() => {
    // Auto-navigate when the scan finishes — same URL, but the page frontmatter
    // re-fetches and renders the complete branch.
    if (state.status === 'completed') {
      window.location.reload()
    }
  }, [state.status])

  const startTimeMs = useMemo(() => (startedAt ? Date.parse(startedAt) : Date.now()), [startedAt])
  const elapsedSeconds = Math.max(0, Math.floor((Date.now() - startTimeMs) / 1000))

  const currentDetector = state.events
    .slice()
    .reverse()
    .find((e) => e.status === 'running')

  return (
    <section className="scan-progress-board" aria-label="Scan in progress">
      <div className="scan-progress-board-kpis">
        <article className="scan-progress-board-kpi">
          <span className="eyebrow eyebrow-rule">TARGET</span>
          <code>{target ?? '—'}</code>
        </article>
        <article className="scan-progress-board-kpi">
          <span className="eyebrow eyebrow-rule">SCAN ID</span>
          <code>{scanId.slice(0, 8)}</code>
        </article>
        <article className="scan-progress-board-kpi scan-progress-board-kpi-loud">
          <span className="eyebrow eyebrow-rule">ELAPSED</span>
          <span className="loud-num">{elapsedSeconds}s</span>
        </article>
        <article className="scan-progress-board-kpi scan-progress-board-kpi-loud">
          <span className="eyebrow eyebrow-rule">ETA</span>
          <span className="loud-num">~{Math.max(0, 30 - elapsedSeconds)}s</span>
        </article>
      </div>

      <ScanProgressBar
        completionPct={state.completionPct}
        progressLabel={`${state.events.length} events received`}
        currentDetector={currentDetector?.payload?.target?.toString() ?? state.currentStage}
      />

      <div className="scan-progress-board-stages">
        {VISIBLE_STAGES.map((stage) => (
          <ScanStageCard
            key={stage.key}
            index={stage.index}
            name={stage.name}
            description={stage.description}
            status={_stageStatus(
              state.stageStatuses[stage.key as keyof typeof state.stageStatuses]
            )}
          />
        ))}
      </div>

      {currentDetector ? (
        <section className="scan-progress-board-active" aria-label="Active detector">
          <DetectorCard
            ruleId={String(currentDetector.payload?.rule_id ?? currentDetector.stage.toUpperCase())}
            status="running"
            filePath={String(currentDetector.payload?.target ?? '')}
            elapsedMs={1000}
          />
        </section>
      ) : null}

      {state.status === 'failed' ? (
        <div className="scan-progress-board-error" role="alert">
          <p>The scan failed. The error has been logged; you can try again or open an issue.</p>
        </div>
      ) : null}
    </section>
  )
}
