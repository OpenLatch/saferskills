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

export async function listTrendingScans({
  limit = 3,
}: {
  limit?: number
} = {}): Promise<ScanReportSummary[]> {
  return fetchScans({
    source: 'trending',
    limit: String(limit),
    order: 'installs_desc',
  })
}
