import { useEffect, useState } from 'react'
import { isReportable } from '@/lib/api/agent-scan-types'
import { fetchAgentScanRunById, fetchAgentScanUnlistedReport } from '@/lib/api/agent-scans'

/**
 * Lightweight pre-grade "auditing…" board for an Agent Report. A scan in
 * `created`/`fetched`/`submitted` shows this and polls the page's OWN tokenless GET
 * (`/agent-scans/{id}` public, `/agent-scans/r/{token}` unlisted) every few seconds —
 * NOT the token-gated `/{id}/status` endpoint, which the web page can't authenticate.
 * When the run becomes `graded`/`published` (or, unlisted, is promoted) it reloads so
 * the SSR route renders the full report. Not the rich SSE scan board — a simple poll.
 */
const POLL_MS = 3500

export default function AgentScanPollBoard({
  runId,
  token,
  target,
  ruleCount,
}: {
  runId?: string
  token?: string
  target: string
  ruleCount: number
}) {
  const [elapsed, setElapsed] = useState(0)

  useEffect(() => {
    let alive = true
    const tick = setInterval(() => setElapsed((s) => s + 1), 1000)

    async function poll() {
      try {
        if (token) {
          const r = await fetchAgentScanUnlistedReport(token)
          if (!alive) return
          if (r.status === 'promoted' || (r.status === 'ok' && isReportable(r.report.status))) {
            window.location.reload()
            return
          }
        } else if (runId) {
          const run = await fetchAgentScanRunById(runId)
          if (!alive) return
          if (run && isReportable(run.status)) {
            window.location.reload()
            return
          }
        }
      } catch {
        /* transient — keep polling */
      }
    }

    const id = setInterval(poll, POLL_MS)
    return () => {
      alive = false
      clearInterval(id)
      clearInterval(tick)
    }
  }, [runId, token])

  return (
    <section className="container" aria-live="polite" aria-busy="true">
      <div className="sr-stat-band">
        <div className="sr-stat-grid">
          <div className="score-cell">
            <div className="sc-label">
              <span className="lab">Auditing {target}…</span>
              <span className="tag">behavioral agent scan</span>
            </div>
            <div className="dots" aria-hidden="true">
              {'●'.repeat((elapsed % 4) + 1)}
              {'○'.repeat(3 - (elapsed % 4))}
            </div>
            <p className="sc-note">
              Running the open adversarial pack — <b>{ruleCount}</b> detectors across the OWASP
              Agentic + MITRE ATLAS families. This page refreshes itself when grading completes.
            </p>
          </div>
          <div className="sr-facts">
            <div className="sb-eyebrow">Status</div>
            <div className="fact">
              <span>State</span>
              <b>auditing</b>
            </div>
            <div className="fact">
              <span>Elapsed</span>
              <b>{elapsed}s</b>
            </div>
            <a className="sr-method" href="/methodology">
              View methodology →
            </a>
          </div>
        </div>
      </div>
    </section>
  )
}
