/**
 * Agent Scan report data layer (I-5.6 Phase A, D-5.6-04).
 *
 * Parallels `scans.ts`: same-origin `/api/*` proxy fetches, generic-404 on miss,
 * and the `redirect:'manual'` unlisted pattern. The API prefix is
 * `/api/v1/agent-scans/*`; the WEB page routes are `/agents/*` (D-5.6-17). The DTO
 * is hand-written in `agent-scan-types.ts` (the generated agent Zod is a stub).
 */

import { env } from '@/env'
import { type AgentScanReportDetail, asAgentScanReportDetail } from './agent-scan-types'

export type { AgentScanReportDetail } from './agent-scan-types'

/** Strip any transcript the public projection should never carry (D-5.6-03,
 * belt-and-suspenders: the server already guarantees `evidence_excerpt:null`). */
function stripPublicEvidence(report: AgentScanReportDetail): AgentScanReportDetail {
  if (report.findings.some((f) => f.evidence_excerpt !== null)) {
    return {
      ...report,
      findings: report.findings.map((f) => ({ ...f, evidence_excerpt: null })),
    }
  }
  return report
}

/** GET /api/v1/agent-scans/{id} — the PUBLIC projection (no transcript). 404 → null. */
export async function fetchAgentScanRunById(id: string): Promise<AgentScanReportDetail | null> {
  const res = await fetch(`${env.PUBLIC_API_URL}/api/v1/agent-scans/${encodeURIComponent(id)}`, {
    headers: { Accept: 'application/json' },
  })
  if (res.status === 404) return null
  if (!res.ok) throw new Error(`API ${res.status}`)
  const report = asAgentScanReportDetail(await res.json())
  return report ? stripPublicEvidence(report) : null
}

export type UnlistedAgentReportResult =
  | { status: 'ok'; report: AgentScanReportDetail }
  /** A promoted run — caller redirects to the public report page. */
  | { status: 'promoted'; reportPath: string }
  | { status: 'not_found' }

/**
 * GET /api/v1/agent-scans/r/{token} — the TOKEN projection (hydrates the redacted
 * transcript). A promoted run answers 307 → the public API route; we read the
 * Location with `redirect:'manual'` and hand back a WEB path (`/agents/{id}`) so SSR
 * never silently follows the redirect to the API origin. Invalid/expired/deleted →
 * generic `not_found` (no oracle).
 */
export async function fetchAgentScanUnlistedReport(
  token: string
): Promise<UnlistedAgentReportResult> {
  const res = await fetch(
    `${env.PUBLIC_API_URL}/api/v1/agent-scans/r/${encodeURIComponent(token)}`,
    { headers: { Accept: 'application/json' }, redirect: 'manual' }
  )
  if (res.status === 307 || res.status === 308 || res.type === 'opaqueredirect') {
    const loc = res.headers.get('Location') ?? ''
    const runId = loc.match(/\/agent-scans\/([^/?#]+)/)?.[1]
    return { status: 'promoted', reportPath: runId ? `/agents/${runId}` : '/' }
  }
  if (res.status === 404) return { status: 'not_found' }
  if (!res.ok) throw new Error(`API ${res.status}`)
  const report = asAgentScanReportDetail(await res.json())
  return report ? { status: 'ok', report } : { status: 'not_found' }
}

/** POST /api/v1/agent-scans/r/{token}/promote — unlisted → public (one-way). Returns
 * the now-public run's id so the manage bar can navigate to `/agents/{id}`. */
export async function promoteAgentUnlisted(token: string): Promise<{ id: string }> {
  const res = await fetch(
    `${env.PUBLIC_API_URL}/api/v1/agent-scans/r/${encodeURIComponent(token)}/promote`,
    { method: 'POST', headers: { Accept: 'application/json' } }
  )
  if (res.status === 404) throw new Error('not_found')
  if (!res.ok) throw new Error(`API ${res.status}`)
  const body = (await res.json()) as { id?: unknown }
  if (typeof body.id !== 'string') throw new Error('bad_response')
  return { id: body.id }
}

/** DELETE /api/v1/agent-scans/r/{token} — eager self-delete (token → generic 404 after). */
export async function deleteAgentUnlisted(token: string): Promise<void> {
  const res = await fetch(
    `${env.PUBLIC_API_URL}/api/v1/agent-scans/r/${encodeURIComponent(token)}`,
    {
      method: 'DELETE',
      headers: { Accept: 'application/json' },
    }
  )
  if (res.status === 404) return
  if (!res.ok) throw new Error(`API ${res.status}`)
}

/** POST /api/v1/agent-scans/verify-waitlist — records verify-tier demand (built in
 * Phase C). Tolerates a dev 404 (endpoint not yet deployed) so the UI scaffold works. */
export async function requestVerifyWaitlist(runId: string, email: string | null): Promise<void> {
  const res = await fetch(`${env.PUBLIC_API_URL}/api/v1/agent-scans/verify-waitlist`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: JSON.stringify({ run_id: runId, email }),
  })
  if (res.ok || res.status === 404) return
  throw new Error(`API ${res.status}`)
}

/** POST /api/v1/agent-scans/{id}/reply — attaches a ≤500-char public vendor reply
 * (built in Phase C). Tolerates a dev 404 like the waitlist endpoint. */
export async function submitAgentReply(runId: string, body: string): Promise<void> {
  const res = await fetch(
    `${env.PUBLIC_API_URL}/api/v1/agent-scans/${encodeURIComponent(runId)}/reply`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify({ body }),
    }
  )
  if (res.ok || res.status === 404) return
  throw new Error(`API ${res.status}`)
}
