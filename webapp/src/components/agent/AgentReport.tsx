import AgentVerb from '@ui/components/atoms/AgentVerb'
import BandPill from '@ui/components/atoms/BandPill'
import CapCallout from '@ui/components/atoms/CapCallout'
import Dialog from '@ui/components/atoms/Dialog'
import DotStrip from '@ui/components/atoms/DotStrip'
import SegmentedTabs, { panelId } from '@ui/components/atoms/SegmentedTabs'
import Toast, { flashToast } from '@ui/components/atoms/Toast'
import TrustTierPill from '@ui/components/atoms/TrustTierPill'
import ProofOfTestsTable from '@ui/components/molecules/ProofOfTestsTable'
import RightOfReplyForm from '@ui/components/molecules/RightOfReplyForm'
import VerifyWaitlistTile from '@ui/components/molecules/VerifyWaitlistTile'
import { useEffect, useId, useRef, useState } from 'react'
import { downloadReportMarkdown } from '@/lib/agent-report-markdown'
import { track } from '@/lib/analytics'
import type { AgentBand, AgentScanReportDetail } from '@/lib/api/agent-scan-types'
import {
  deleteAgentUnlisted,
  promoteAgentUnlisted,
  requestVerifyWaitlist,
  submitAgentReply,
} from '@/lib/api/agent-scans'

type TabId = 'report' | 'findings' | 'component'
const TABS_ORDER: TabId[] = ['report', 'findings', 'component']
const ID_BASE = 'agent-report'

const CELL_CLASS: Record<Exclude<AgentBand, 'unscoped'>, string> = {
  green: 'g',
  yellow: 'y',
  orange: 'o',
  red: 'r',
}

/** The launch trust pill shows the trust TIER only (the wider trust_labels enum
 * surfaces as provenance chips in Phase B). */
function tierLabels(labels: string[]): string[] {
  const tier = labels.filter((l) => l === 'cloud-validated' || l === 'client-administered')
  return tier.length > 0 ? tier : ['cloud-validated', 'client-administered']
}

interface Props {
  run: AgentScanReportDetail
  shareUrl: string
  /** Total active detection rules (footer/methodology context). */
  ruleCount: number
  /** Token route → manage bar + right-of-reply; public → copy-link only. */
  unlisted?: boolean
  token?: string
}

export default function AgentReport({ run, shareUrl, unlisted = false, token }: Props) {
  const [tab, setTab] = useState<TabId>('report')
  const promoteRef = useRef<HTMLDialogElement | null>(null)
  const deleteRef = useRef<HTMLDialogElement | null>(null)
  const promoteTitle = useId()
  const deleteTitle = useId()
  const [busy, setBusy] = useState(false)
  const [manageError, setManageError] = useState<string | null>(null)

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

  function viewFinding(_testId: string) {
    selectTab('findings')
  }

  async function onShare() {
    try {
      await navigator.clipboard.writeText(shareUrl)
      flashToast('Report link copied')
    } catch {
      flashToast('Copy failed — select the URL manually')
    }
    track('agent_report_shared', {})
  }

  function onExport() {
    downloadReportMarkdown(run)
    track('agent_report_exported', {})
  }

  async function onVerify(email: string | null) {
    await requestVerifyWaitlist(run.id, email)
    track('agent_report_verify_requested', {})
  }

  async function onReply(body: string) {
    await submitAgentReply(run.id, body)
    track('agent_report_reply_submitted', {})
  }

  async function confirmPromote() {
    if (!token) return
    setBusy(true)
    setManageError(null)
    try {
      const { id } = await promoteAgentUnlisted(token)
      window.location.assign(`/agents/${id}`)
    } catch {
      setManageError('Could not promote this report — please try again.')
      setBusy(false)
    }
  }

  async function confirmDelete() {
    if (!token) return
    setBusy(true)
    setManageError(null)
    try {
      await deleteAgentUnlisted(token)
      window.location.assign('/agents')
    } catch {
      setManageError('Could not delete this report — please try again.')
      setBusy(false)
    }
  }

  const tier4 = run.band === 'unscoped' ? null : run.band
  const cellClass = run.band === 'unscoped' ? '' : CELL_CLASS[run.band]
  const score = run.score ?? 0
  const capCount = run.capabilities_present.length
  const scannedDate = run.scanned_at ? run.scanned_at.slice(0, 10) : '—'
  const hasFindings = run.findings.length > 0

  return (
    <section className="container" aria-label="Agent scan report">
      {/* meta + manage/share cluster */}
      <div className="sr-head-row">
        <div className="sr-head-l">
          <div className="sr-head-meta">
            scanned {scannedDate} · {run.runtime} · {capCount} capabilities
          </div>
        </div>
        <div className="sr-head-r">
          <div className="manage-bar">
            <button type="button" className="mbtn primary" onClick={onShare}>
              ⧉ Share with your security team
            </button>
            <button type="button" className="mbtn" onClick={onExport}>
              ↧ Export Markdown
            </button>
            {unlisted && (
              <>
                <button
                  type="button"
                  className="mbtn"
                  onClick={() => promoteRef.current?.showModal()}
                >
                  ↥ Promote to public
                </button>
                <button
                  type="button"
                  className="mbtn mbtn-danger"
                  onClick={() => deleteRef.current?.showModal()}
                >
                  Delete
                </button>
              </>
            )}
          </div>
        </div>
      </div>

      {/* behavioral score hero */}
      <section className="sr-stat-band">
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
            <div className="ar-scoreline">
              {tier4 && <DotStrip value={score} tier={tier4} />}
              {tier4 && <BandPill tier={tier4} />}
              <AgentVerb band={run.band} />
              <TrustTierPill labels={tierLabels(run.trust_labels)} />
            </div>
            {run.cap_callout && <CapCallout band={run.band} text={run.cap_callout} />}
          </div>

          <div className="sr-facts">
            <div className="sb-eyebrow">This scan</div>
            <div className="fact">
              <span>Agent</span>
              <b>{run.agent_name}</b>
            </div>
            <div className="fact">
              <span>Capabilities</span>
              <b>{capCount}</b>
            </div>
            <div className="fact">
              <span>Tests</span>
              <b>{run.checks.length}</b>
            </div>
            <div className="fact">
              <span>Findings</span>
              <b>{run.findings.length}</b>
            </div>
            <a className="sr-method" href="/methodology">
              View methodology →
            </a>
          </div>
        </div>
      </section>

      {/* tab shell */}
      <SegmentedTabs
        variant="underline"
        idBase={ID_BASE}
        ariaLabel="Agent report sections"
        value={tab}
        onChange={selectTab}
        tabs={[
          { id: 'report', label: 'Report', count: run.checks.length },
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
        {hasFindings && (
          <p className="ar-panel-lead">
            <b>One critical behavior caps the grade</b> regardless of how the rest scored.
          </p>
        )}
        <ProofOfTestsTable checks={run.checks} onViewFinding={viewFinding} />
      </div>

      <div
        role="tabpanel"
        id={panelId(ID_BASE, 'findings')}
        aria-labelledby={`${ID_BASE}-tab-findings`}
        className="ar-panel"
        hidden={tab !== 'findings'}
      >
        <p className="ar-tab-placeholder">
          {hasFindings
            ? `${run.findings.length} finding(s) — OWASP-grouped detail, evidence and remediation land in the next release.`
            : 'No findings — the full OWASP Agentic + MITRE ATLAS pack passed.'}
        </p>
      </div>

      <div
        role="tabpanel"
        id={panelId(ID_BASE, 'component')}
        aria-labelledby={`${ID_BASE}-tab-component`}
        className="ar-panel"
        hidden={tab !== 'component'}
      >
        <p className="ar-tab-placeholder">
          Contributing context only — never fused into the behavioral score. Per-capability scores
          land in the next release.
        </p>
      </div>

      {/* lifecycle: waitlist (every report) + right-of-reply (token holder) */}
      <div className="ar-lifecycle">
        <VerifyWaitlistTile onSubmit={onVerify} />
        {unlisted && <RightOfReplyForm onSubmit={onReply} />}
      </div>

      {unlisted && (
        <>
          <Dialog
            dialogRef={promoteRef}
            titleId={promoteTitle}
            title="Promote to public?"
            description="This makes the report public and permanent, and removes the 90-day expiry. It cannot be undone."
            error={manageError}
            pending={busy}
            confirmLabel="Promote to public"
            pendingLabel="Promoting…"
            onConfirm={confirmPromote}
          />
          <Dialog
            dialogRef={deleteRef}
            titleId={deleteTitle}
            title="Delete this report?"
            description="Anyone with the link loses access immediately. This cannot be undone."
            error={manageError}
            pending={busy}
            confirmLabel="Delete permanently"
            pendingLabel="Deleting…"
            confirmVariant="danger"
            onConfirm={confirmDelete}
          />
        </>
      )}

      <Toast />
    </section>
  )
}
