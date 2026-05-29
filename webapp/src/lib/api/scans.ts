import { env } from '@/env'

export type ScanTier = 'green' | 'yellow' | 'orange' | 'red' | 'unscoped'

export type ScanReportSummary = {
  id: string
  github_url: string
  slug: string
  aggregate_score: number
  tier: ScanTier
  scanned_at: string
  findings_count?: number
  author?: string
  title?: string
}

interface ListEnvelope<T> {
  data: T[]
  next_cursor?: string | null
}

async function fetchScans(params: Record<string, string>): Promise<ScanReportSummary[]> {
  const url = new URL(`${env.PUBLIC_API_URL}/api/v1/scans`)
  for (const [k, v] of Object.entries(params)) url.searchParams.set(k, v)
  const res = await fetch(url, { headers: { Accept: 'application/json' } })
  if (!res.ok) throw new Error(`API ${res.status}`)
  const body = (await res.json()) as ListEnvelope<ScanReportSummary>
  return body.data ?? []
}

export async function listRecentSubmissionScans({
  limit = 4,
}: {
  limit?: number
} = {}): Promise<ScanReportSummary[]> {
  return fetchScans({
    source: 'submission',
    limit: String(limit),
    order: 'created_at_desc',
  })
}

export async function listTrendingScans(
  _opts: { limit?: number } = {}
): Promise<ScanReportSummary[]> {
  // TODO(I-05): wire to real install counts. Install tracking ships with the
  // install CLI (I-05); until then `source=trending&order=installs_desc` has no
  // valid backend mapping and would 422. Return empty so the caller cleanly
  // falls back to the launch placeholder — no 422 / Sentry noise.
  return []
}

export interface Finding {
  id: string
  rule_id: string
  severity: 'info' | 'low' | 'medium' | 'high' | 'critical'
  sub_score: 'security' | 'supply_chain' | 'maintenance' | 'transparency' | 'community'
  penalty: number
  status_at_scan: 'shadow' | 'active'
  file_path: string
  line_start: number
  line_end?: number | null
  matched_content_sha256: string
  remediation_link: string
  rubric_version: string
}

export interface ScanReportDetail {
  id: string
  github_url: string
  slug: string
  display_name: string
  aggregate_score: number
  tier: ScanTier
  sub_scores: Record<string, number>
  score_breakdown: Record<string, unknown>
  findings: Finding[]
  scanned_at: string
  rubric_version: string
  engine_version: string
  latency_ms: number
  source: string
  status: 'pending' | 'running' | 'completed' | 'failed'
  ref_sha: string
}

export async function fetchScanById(scanId: string): Promise<ScanReportDetail | null> {
  const res = await fetch(`${env.PUBLIC_API_URL}/api/v1/scans/${encodeURIComponent(scanId)}`, {
    headers: { Accept: 'application/json' },
  })
  if (res.status === 404) return null
  if (!res.ok) throw new Error(`API ${res.status}`)
  return (await res.json()) as ScanReportDetail
}

export interface ScanSubmitRequest {
  github_url: string
  rescan?: boolean
}

export interface ScanSubmitResponse {
  id: string
  status: 'pending' | 'running' | 'completed' | 'failed'
  cached: boolean
  rubric_version: string
  submitted_at: string
}

export async function submitScan(body: ScanSubmitRequest): Promise<ScanSubmitResponse> {
  const res = await fetch(`${env.PUBLIC_API_URL}/api/v1/scans`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: JSON.stringify(body),
  })
  if (res.status === 429) throw new Error('rate_limit_exceeded')
  if (res.status === 422) throw new Error('invalid_url')
  if (!res.ok) throw new Error(`API ${res.status}`)
  return (await res.json()) as ScanSubmitResponse
}
