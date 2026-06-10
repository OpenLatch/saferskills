import type { AgentScanReportDetail } from './api/agent-scan-types'

/**
 * Export an Agent Report as Markdown (I-5.6 D-5.6-11).
 *
 * PHASE A STUB: returns a minimal header (identity + score + verdict + provenance).
 * The full serializer — findings, OWASP/MITRE refs, score-math, remediation — lands
 * in Phase B. A PUBLIC export NEVER includes transcript/evidence (route-driven
 * split, D-5.6-03); this stub carries none by construction.
 */
export function exportReportMarkdown(run: AgentScanReportDetail): string {
  const scoreLine = run.score === null ? '—' : `${run.score}/100`
  const lines = [
    `# Agent Scan — ${run.agent_name}`,
    '',
    `- **Behavioral score:** ${scoreLine} (${run.band.toUpperCase()})`,
    run.verdict_label ? `- **Verdict:** ${run.verdict_label}` : null,
    `- **Runtime:** ${run.runtime}`,
    `- **Pack:** ${run.pack_id} @ ${run.pack_version}`,
    `- **Findings:** ${run.findings.length}`,
    run.report_url ? `- **Report:** ${run.report_url}` : null,
    '',
    '_Full Markdown export (findings, score-math, remediation) lands in I-5.6 Phase B._',
    '',
  ]
  return lines.filter((l) => l !== null).join('\n')
}

/** Trigger a client-side `.md` download of the serialized report. */
export function downloadReportMarkdown(run: AgentScanReportDetail): void {
  if (typeof window === 'undefined') return
  const blob = new Blob([exportReportMarkdown(run)], { type: 'text/markdown' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `agent-scan-${run.id.slice(0, 8)}.md`
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}
