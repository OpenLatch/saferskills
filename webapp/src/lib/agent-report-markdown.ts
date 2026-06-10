import { groupFindingsByFamily } from './agent/findings-view'
import type { AgentFindingRow, AgentScanReportDetail } from './api/agent-scan-types'

/**
 * Export an Agent Report as Markdown (I-5.6 D-5.6-11) — the full client-side
 * serializer. Emits identity + score/band/verdict + cap callout + trust labels +
 * per-OWASP-family findings (id, severity, refs, why-it-matters, score-math
 * summary, remediation) + provenance.
 *
 * Route-driven evidence split (D-5.6-03): a finding's transcript is serialized
 * ONLY when `evidence_excerpt` is present — i.e. on the unlisted token route. A
 * PUBLIC export carries `evidence_excerpt: null` on every finding, so no
 * transcript is ever written. No OpenLatch mention anywhere (D-5.6-13).
 */

function scoreLine(run: AgentScanReportDetail): string {
  const s = run.score === null ? '—' : `${run.score}/100`
  return `- **Behavioral score:** ${s} (${run.band.toUpperCase()})`
}

function findingRefs(f: AgentFindingRow): string {
  const refs = [...(f.owasp_refs ?? []), ...(f.atlas_refs ?? []), ...(f.nist_refs ?? [])]
  return refs.length > 0 ? refs.join(' · ') : ''
}

function scoreImpact(run: AgentScanReportDetail, f: AgentFindingRow): string | null {
  const bd = run.score_breakdown
  if (!bd) return null
  const own = bd.findings.find((m) => m.test_id === f.test_id)
  const delta = own ? (own.score_delta > 0 ? `+${own.score_delta}` : `${own.score_delta}`) : '0'
  const cap = bd.ceiling_applied && bd.ceiling !== null ? `, worst-finding cap → ${bd.ceiling}` : ''
  return `**Score impact:** ${delta}${cap}; final ${bd.final_score}/100`
}

/** Remediation block for a single finding (reused by the per-card Copy button). */
export function findingRemediationMarkdown(f: AgentFindingRow): string {
  const out: string[] = []
  const r = f.remediation
  if (r?.action) out.push(`**Remediation:** ${r.action}`)
  if (r?.steps && r.steps.length > 0) {
    for (const step of r.steps) out.push(`- ${step}`)
  }
  if (r?.safer_pattern) {
    out.push('```diff')
    out.push(`- ${r.safer_pattern.before}`)
    out.push(`+ ${r.safer_pattern.after}`)
    out.push('```')
  }
  return out.join('\n')
}

/** Verbatim transcript window — ONLY emitted when `evidence_excerpt` is present
 * (unlisted token route). Never reached on a public export (null evidence). */
function findingTranscript(f: AgentFindingRow): string {
  const ex = f.evidence_excerpt
  if (!ex?.lines || ex.lines.length === 0) return ''
  const out: string[] = [`**Redacted transcript** (${ex.file}):`, '```']
  for (const line of ex.lines) {
    const mark = line.hit ? ' « leaked canary' : ''
    out.push(`${line.line_no}: ${line.text}${mark}`)
  }
  out.push('```')
  return out.join('\n')
}

function findingSection(run: AgentScanReportDetail, f: AgentFindingRow): string[] {
  const sev = (f.severity ?? 'info').toUpperCase()
  const title = f.title || f.test_id
  const lines: string[] = [`#### ${f.test_id} — ${title} (${sev})`]
  const refs = findingRefs(f)
  if (refs) lines.push(`_${refs}_`)
  if (f.explanation) lines.push('', f.explanation)
  const impact = scoreImpact(run, f)
  if (impact) lines.push('', impact)
  const rem = findingRemediationMarkdown(f)
  if (rem) lines.push('', rem)
  const transcript = findingTranscript(f)
  if (transcript) lines.push('', transcript)
  return lines
}

export function exportReportMarkdown(run: AgentScanReportDetail): string {
  const lines: (string | null)[] = [
    `# Agent Scan — ${run.agent_name}`,
    '',
    scoreLine(run),
    run.verdict_label ? `- **Verdict:** ${run.verdict_label}` : null,
    `- **Runtime:** ${run.runtime}`,
    `- **Pack:** ${run.pack_id} @ ${run.pack_version}`,
    `- **Findings:** ${run.findings.length}`,
    run.report_url ? `- **Report:** ${run.report_url}` : null,
  ]
  if (run.cap_callout) lines.push('', `> ${run.cap_callout}`)
  if (run.trust_labels.length > 0) lines.push('', `_Trust: ${run.trust_labels.join(' · ')}_`)

  if (run.findings.length > 0) {
    lines.push('', '## Findings')
    for (const group of groupFindingsByFamily(run.findings)) {
      lines.push('', `### ${group.index ? `${group.index} · ` : ''}${group.family}`)
      for (const f of group.findings) lines.push('', ...findingSection(run, f))
    }
  }

  lines.push(
    '',
    '## Provenance',
    `- Scan: scn_${run.id.slice(0, 8)}`,
    `- Pack: ${run.pack_id}@${run.pack_version}${run.pack_signature_verified ? ' (signature verified)' : ''}`,
    `- Rubric: ${run.rubric_version} · Engine: ${run.engine_version}`,
    run.scanned_at ? `- Scanned: ${run.scanned_at.slice(0, 10)}` : null,
    ''
  )
  return lines.filter((l) => l !== null).join('\n')
}

/** Remediation-only export — "export all fixes as checklist" (D-5.6-11 §B4). */
export function exportRemediationChecklist(run: AgentScanReportDetail): string {
  const lines: string[] = [`# Agent Scan remediation checklist — ${run.agent_name}`, '']
  if (run.findings.length === 0) {
    lines.push('No findings — nothing to remediate.', '')
    return lines.join('\n')
  }
  for (const f of run.findings) {
    lines.push(`## ${f.test_id} — ${f.title || f.test_id}`)
    const rem = findingRemediationMarkdown(f)
    lines.push(rem || '_No remediation recorded._', '')
  }
  return lines.join('\n')
}

function downloadMarkdown(markdown: string, filename: string): void {
  if (typeof window === 'undefined') return
  const blob = new Blob([markdown], { type: 'text/markdown' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}

/** Trigger a client-side `.md` download of the full serialized report. */
export function downloadReportMarkdown(run: AgentScanReportDetail): void {
  downloadMarkdown(exportReportMarkdown(run), `agent-scan-${run.id.slice(0, 8)}.md`)
}

/** Trigger a client-side `.md` download of the remediation checklist only. */
export function downloadRemediationChecklist(run: AgentScanReportDetail): void {
  downloadMarkdown(
    exportRemediationChecklist(run),
    `agent-scan-${run.id.slice(0, 8)}-remediation.md`
  )
}
