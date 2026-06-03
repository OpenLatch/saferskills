import CopyIconButton from '@ui/components/atoms/CopyIconButton'
import ScanProgressBar from '@ui/components/molecules/ScanProgressBar'
import ScanStepper, { type ScanStep } from '@ui/components/molecules/ScanStepper'
import ScanTerminal from '@ui/components/molecules/ScanTerminal'
import { useEffect, useMemo, useState } from 'react'

import { useScanProgress } from '@/lib/hooks/useScanProgress'
import { buildTerminalLines, formatTarget } from './terminal-feed'

interface Props {
  scanId: string
  /** Initial target — rendered before the SSE channel opens. */
  target?: string
  /** Seeds the live elapsed counter. */
  startedAt?: string
}

/** The four user-facing stages + their progress windows + plain-language copy. */
const VISIBLE_STAGES = [
  {
    index: '01',
    name: 'Fetch',
    key: 'fetch',
    tag: 'clone',
    description:
      'Clone the repo at the pinned commit and walk every file. Nothing is run — files are read as data.',
    range: [0, 25],
  },
  {
    index: '02',
    name: 'Security',
    key: 'security',
    tag: 'rules',
    description:
      'Check each file for prompt-injection, remote-code-execution, and secret-exfiltration patterns.',
    range: [25, 55],
  },
  {
    index: '03',
    name: 'Supply chain',
    key: 'supply_chain',
    tag: 'deps',
    description:
      'Inspect dependencies and bundles for typosquats, version drift, and unsigned packages.',
    range: [55, 80],
  },
  {
    index: '04',
    name: 'Score & sign',
    key: 'sign',
    tag: 'verdict',
    description:
      'Aggregate the sub-scores under the critical-floor rule, then cryptographically sign the report.',
    range: [80, 100],
  },
] as const

function clampWithin(pct: number, [a, b]: readonly [number, number]): number {
  if (b <= a) return pct >= b ? 100 : 0
  return Math.max(0, Math.min(100, ((pct - a) / (b - a)) * 100))
}

function usePrefersReducedMotion(): boolean {
  const [reduced, setReduced] = useState(false)
  useEffect(() => {
    if (typeof window === 'undefined' || !window.matchMedia) return undefined
    const mq = window.matchMedia('(prefers-reduced-motion: reduce)')
    setReduced(mq.matches)
    const handler = (e: MediaQueryListEvent) => setReduced(e.matches)
    mq.addEventListener('change', handler)
    return () => mq.removeEventListener('change', handler)
  }, [])
  return reduced
}

export default function ScanProgressBoard({ scanId, target, startedAt }: Props) {
  const state = useScanProgress(scanId)
  const reducedMotion = usePrefersReducedMotion()
  const isComplete = state.status === 'completed'
  const isFailed = state.status === 'failed'

  useEffect(() => {
    // When the scan finishes, re-render the page — the frontmatter re-fetches
    // and swaps to the completed report branch.
    if (state.status === 'completed') window.location.reload()
  }, [state.status])

  // Live-ticking elapsed / ETA.
  const startMs = useMemo(() => {
    const parsed = startedAt ? Date.parse(startedAt) : Number.NaN
    return Number.isNaN(parsed) ? Date.now() : parsed
  }, [startedAt])
  const [nowMs, setNowMs] = useState(() => Date.now())
  useEffect(() => {
    if (isComplete || isFailed) return undefined
    const timer = window.setInterval(() => setNowMs(Date.now()), 1000)
    return () => window.clearInterval(timer)
  }, [isComplete, isFailed])
  const elapsed = Math.max(0, Math.floor((nowMs - startMs) / 1000))
  const eta = Math.max(0, 30 - elapsed)

  const { host, ref } = formatTarget(target)

  const steps: ScanStep[] = VISIBLE_STAGES.map((stage) => {
    const status = state.stageStatuses[stage.key] ?? 'pending'
    const within = clampWithin(state.completionPct, stage.range)
    return {
      key: stage.key,
      index: stage.index,
      name: stage.name,
      tag: stage.tag,
      description: stage.description,
      status,
      fillPct: status === 'completed' ? 100 : status === 'running' ? within : 0,
      runningPct: within,
    }
  })

  const runningStage = VISIBLE_STAGES.find((s) => state.stageStatuses[s.key] === 'running')
  const currentLabel = isComplete
    ? 'complete'
    : runningStage
      ? runningStage.name.toLowerCase()
      : state.completionPct > 0
        ? 'scanning'
        : 'starting'
  const completedCount = steps.filter((s) => s.status === 'completed').length

  const lines = useMemo(() => buildTerminalLines(state.events, target), [state.events, target])

  return (
    <section className="scan-progress-board" aria-label="Scan in progress">
      {/* instrument bar */}
      <div className="scan-ib">
        <div className="scan-ib-cell scan-ib-target">
          <span className="scan-ib-l">Target</span>
          <span className="scan-ib-val">
            <span className="scan-ib-host" title={target ?? undefined}>
              {host}
            </span>
            {ref ? <span className="scan-ib-ref">@{ref}</span> : null}
          </span>
        </div>
        <div className="scan-ib-cell">
          <span className="scan-ib-l">Scan</span>
          <span className="scan-ib-val">
            <code>{scanId.slice(0, 8)}</code>
            <CopyIconButton value={scanId} label="Copy scan ID" />
          </span>
        </div>
        <div className="scan-ib-cell">
          <span className="scan-ib-l">Elapsed</span>
          <span className="scan-ib-val">{elapsed}s</span>
        </div>
        <div className="scan-ib-cell">
          <span className="scan-ib-l">ETA</span>
          <span className="scan-ib-val">{isComplete ? 'done' : eta > 0 ? `~${eta}s` : 'soon'}</span>
        </div>
        <div className="scan-ib-cell scan-ib-badge-cell">
          <span
            className={`scan-ib-status ${isComplete ? 'is-complete' : 'is-running'}${reducedMotion ? ' reduced-motion' : ''}`}
          >
            <span className="scan-ib-dot" aria-hidden="true" />
            {isComplete ? 'Signed' : 'Running'}
            {!isComplete ? <span className="scan-ib-shimmer" aria-hidden="true" /> : null}
          </span>
        </div>
      </div>

      {/* two-column run view */}
      <div className="scan-grid">
        <ScanStepper
          steps={steps}
          heading={`Stages · ${VISIBLE_STAGES.length}`}
          currentLabel={currentLabel}
        />
        <ScanTerminal
          lines={lines}
          currentStage={currentLabel}
          complete={isComplete}
          reducedMotion={reducedMotion}
        />
      </div>

      {/* foot meter */}
      <div className="scan-foot">
        <ScanProgressBar
          completionPct={state.completionPct}
          progressLabel={`${completedCount}/${VISIBLE_STAGES.length} stages`}
          currentDetector={isComplete ? undefined : currentLabel}
          reducedMotion={reducedMotion}
        />
      </div>

      {isFailed ? (
        <div className="scan-progress-board-error" role="alert">
          <p>The scan failed. The error has been logged; you can try again or open an issue.</p>
        </div>
      ) : null}
    </section>
  )
}
