import CapCallout from '@ui/components/atoms/CapCallout'
import { runtimeLabel } from '@ui/components/atoms/RuntimeMonogram'
import SegmentedTabs, { panelId } from '@ui/components/atoms/SegmentedTabs'
import ComponentScoresTable from '@ui/components/molecules/ComponentScoresTable'
import ProofOfTestsTable from '@ui/components/molecules/ProofOfTestsTable'
import RightOfReplyForm from '@ui/components/molecules/RightOfReplyForm'
import { useEffect, useState } from 'react'
import { downloadRemediationChecklist } from '@/lib/agent-report-markdown'
import { track } from '@/lib/analytics'
import type { AgentBand, AgentScanReportDetail } from '@/lib/api/agent-scan-types'
import { submitAgentReply } from '@/lib/api/agent-scans'
import AgentBadgeBand from './AgentBadgeBand'
import AgentFindings from './AgentFindings'

type TabId = 'report' | 'findings' | 'component'
const TABS_ORDER: TabId[] = ['report', 'findings', 'component']
const ID_BASE = 'agent-report'

const CELL_CLASS: Record<Exclude<AgentBand, 'unscoped'>, string> = {
  green: 'g',
  yellow: 'y',
  orange: 'o',
  red: 'r',
}

/** The facts-panel findings summary — `1 critical · 1 high · 1 medium · 1 info` / `none`. */
function findingsSummary(run: AgentScanReportDetail): string {
  const order = ['critical', 'high', 'medium', 'low', 'info'] as const
  const counts = new Map<string, number>()
  for (const f of run.findings) {
    const sev = f.severity ?? 'info'
    counts.set(sev, (counts.get(sev) ?? 0) + 1)
  }
  const parts = order.filter((s) => counts.has(s)).map((s) => `${counts.get(s)} ${s}`)
  return parts.length > 0 ? parts.join(' · ') : 'none'
}

interface Props {
  run: AgentScanReportDetail
  shareUrl: string
  /** Total active detection rules (footer/methodology context). */
  ruleCount: number
  /** Token route → right-of-reply; public → read-only lifecycle. */
  unlisted?: boolean
  token?: string
}

export default function AgentReport({ run, unlisted = false, token }: Props) {
  const [tab, setTab] = useState<TabId>('report')
  // Cross-tab "View finding →": the finding id to open + a nonce so a repeat
  // request on the same finding re-fires the scroll.
  const [openFindingId, setOpenFindingId] = useState<string | null>(null)
  const [scrollNonce, setScrollNonce] = useState(0)

  // Sync the tab from the URL hash AFTER hydration (SSR always renders #report,
  // so initial markup matches on both sides — no hydration mismatch).
  useEffect(() => {
    const fromHash = (window.location.hash.replace('#', '') || 'report') as TabId
    if (TABS_ORDER.includes(fromHash)) setTab(fromHash)
    const onHash = () => {
      const h = (window.location.hash.replace('#', '') || 'report') as TabId
      if (TABS_ORDER.includes(h)) setTab(h)
    }
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [])

  function selectTab(id: string) {
    const t = id as TabId
    setTab(t)
    track('agent_report_tab_selected', { tab: t })
    if (typeof window !== 'undefined') history.replaceState(null, '', `#${t}`)
  }

  function viewFinding(testId: string) {
    const target = run.findings.find((f) => f.test_id === testId)
    if (target) setOpenFindingId(target.id)
    setScrollNonce((n) => n + 1)
    selectTab('findings')
  }

  function onExportFixes() {
    downloadRemediationChecklist(run)
    track('agent_report_exported', {})
  }

  async function onReply(body: string) {
    if (!token) return
    await submitAgentReply(token, body)
    track('agent_report_reply_submitted', {})
  }

  const cellClass = run.band === 'unscoped' ? '' : CELL_CLASS[run.band]
  const score = run.score ?? 0
  const dotsFilled = Math.max(0, Math.min(10, Math.round(score / 10)))
  const capCount = run.capabilities_present.length
  const total = run.checks.length
  const failed = run.checks.filter((c) => c.verdict === 'vulnerable').length
  const passed = total - failed
  const hasFindings = run.findings.length > 0

  return (
    <>
      {/* behavioral score hero — full-bleed band (mockup .sr-stat-band) */}
      <section className="sr-stat-band" aria-label="Behavioral agent score">
        <div className="container">
          <div className="sr-stat-grid">
            <div className={`score-cell ${cellClass}`.trim()}>
              <div className="sc-label">
                <span className="lab">Behavioral agent score</span>
                <span className="tag">assembled agent · 0–100</span>
              </div>
              <div className="sr-big">
                {run.score ?? '—'}
                <span className="denom">/100</span>
              </div>
              <div className="dots">
                {cellClass && (
                  <span className={`dot-${cellClass}`} aria-hidden="true">
                    {'●'.repeat(dotsFilled)}
                  </span>
                )}
                <span className="dot-off" aria-hidden="true">
                  {'○'.repeat(10 - dotsFilled)}
                </span>
              </div>
              {run.cap_callout && <CapCallout band={run.band} text={run.cap_callout} />}
            </div>

            <div className="sr-facts">
              <span className="sb-eyebrow">This scan</span>
              <div className="fact">
                <span>Agent</span>
                <b>{runtimeLabel(run.runtime)}</b>
              </div>
              <div className="fact">
                <span>Capabilities</span>
                <b>{capCount} assembled</b>
              </div>
              <div className="fact">
                <span>Tests</span>
                <b>
                  {passed} / {total} passed
                </b>
              </div>
              <div className="fact">
                <span>Findings</span>
                <b>{findingsSummary(run)}</b>
              </div>
              <a className="sr-method" href="/methodology">
                View methodology →
              </a>
            </div>
          </div>
        </div>
      </section>

      {/* tabbed main */}
      <section className="sr-main">
        <div className="container">
          <SegmentedTabs
            variant="underline"
            idBase={ID_BASE}
            ariaLabel="Agent report sections"
            value={tab}
            onChange={selectTab}
            tabs={[
              { id: 'report', label: 'Report', count: `${passed}/${total}` },
              { id: 'findings', label: 'Findings', count: run.findings.length },
              { id: 'component', label: 'Component Scores', count: run.component_scores.length },
            ]}
          />

          <div
            role="tabpanel"
            id={panelId(ID_BASE, 'report')}
            aria-labelledby={`${ID_BASE}-tab-report`}
            className="ar-panel"
            hidden={tab !== 'report'}
          >
            <p className="ar-panel-lead">
              We ran an open adversarial pack (OWASP Agentic + MITRE ATLAS) against the whole
              assembled agent. <b>One critical behavior caps the grade</b> regardless of how the
              rest scored.
            </p>
            <ProofOfTestsTable checks={run.checks} onViewFinding={viewFinding} />
          </div>

          <div
            role="tabpanel"
            id={panelId(ID_BASE, 'findings')}
            aria-labelledby={`${ID_BASE}-tab-findings`}
            className="ar-panel"
            hidden={tab !== 'findings'}
          >
            {hasFindings ? (
              <div className="sr-block">
                <div className="sr-block-head">
                  <h3>
                    Findings<span className="sub">— grouped by OWASP risk family</span>
                  </h3>
                </div>
                <div className="ar-findings-head">
                  <span className="ev-cap">
                    <b>Evidence split:</b>{' '}
                    {unlisted
                      ? 'this private report adds the redacted transcript with the leaked canary highlighted.'
                      : 'the public report shows finding · refs · severity · fix. The private report adds the redacted transcript with the leaked canary highlighted.'}
                  </span>
                  <button type="button" className="ar-export-fixes" onClick={onExportFixes}>
                    <span aria-hidden="true">↧</span> Export all fixes as checklist
                  </button>
                </div>
                <AgentFindings
                  findings={run.findings}
                  scoreBreakdown={run.score_breakdown}
                  unlisted={unlisted}
                  requestOpenId={openFindingId}
                  requestNonce={scrollNonce}
                />
              </div>
            ) : (
              <div className="evidence-public-note">
                <svg
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="var(--score-green)"
                  strokeWidth="2.4"
                  aria-hidden="true"
                >
                  <path d="M20 6 9 17l-5-5" />
                </svg>
                <span>
                  <b>No findings.</b> The agent passed the full OWASP Agentic + MITRE ATLAS pack —
                  there is nothing to remediate.
                </span>
              </div>
            )}
          </div>

          <div
            role="tabpanel"
            id={panelId(ID_BASE, 'component')}
            aria-labelledby={`${ID_BASE}-tab-component`}
            className="ar-panel"
            hidden={tab !== 'component'}
          >
            <ComponentScoresTable rows={run.component_scores} />
          </div>

          {/* an existing vendor right-of-reply renders read-only on every report */}
          {run.vendor_reply && (
            <figure className="ar-vendor-reply">
              <figcaption className="avr-head">
                Vendor right-of-reply
                {run.vendor_reply_at && (
                  <span className="avr-when"> · {run.vendor_reply_at.slice(0, 10)}</span>
                )}
              </figcaption>
              <blockquote className="avr-body">{run.vendor_reply}</blockquote>
            </figure>
          )}

          {/* lifecycle: right-of-reply (token holder only) */}
          {unlisted && (
            <div className="ar-lifecycle">
              <RightOfReplyForm onSubmit={onReply} />
            </div>
          )}
        </div>
      </section>

      {/* README badge embed + provenance — full-bleed band */}
      <AgentBadgeBand run={run} unlisted={unlisted} />
    </>
  )
}
