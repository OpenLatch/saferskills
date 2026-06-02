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

export type CapabilityKind = 'skill' | 'mcp_server' | 'hook' | 'plugin' | 'rules'

export interface FindingsSummary {
  critical: number
  high: number
  medium: number
  low: number
  info: number
  total: number
}

export interface CapabilityRow {
  kind: CapabilityKind
  name: string
  component_path?: string | null
  aggregate_score: number
  tier: ScanTier
  scan_id: string
  catalog_slug: string
  sub_scores: Record<string, number>
  findings_summary: FindingsSummary
  findings: Finding[]
}

export type Visibility = 'public' | 'unlisted'
export type ArtifactSource = 'github' | 'upload'

/** GET /api/v1/scans/runs/<run_id> — the repo scan report (all capabilities). */
export interface ScanRunReportDetail {
  id: string
  /** Null for uploads (no repo coordinates) — P0-9. */
  github_url: string | null
  repo_aggregate_score: number
  repo_tier: ScanTier
  kind_tally: Record<string, number>
  capability_count: number
  capabilities: CapabilityRow[]
  scanned_at: string
  rubric_version: string
  engine_version: string
  latency_ms: number
  source: string
  status: 'pending' | 'running' | 'completed' | 'failed'
  ref_sha?: string | null
  // --- I-3.5 upload + visibility additions ---
  visibility?: Visibility
  source_kind?: ArtifactSource
  artifact_sha256?: string | null
  uploaded_filename?: string | null
  /** Unlisted only — ISO timestamp. */
  expires_at?: string | null
  /** Present only on upload/unlisted responses — never logged. */
  share_url?: string | null
}

export async function fetchScanRunById(runId: string): Promise<ScanRunReportDetail | null> {
  const res = await fetch(`${env.PUBLIC_API_URL}/api/v1/scans/runs/${encodeURIComponent(runId)}`, {
    headers: { Accept: 'application/json' },
  })
  if (res.status === 404) return null
  if (!res.ok) throw new Error(`API ${res.status}`)
  return (await res.json()) as ScanRunReportDetail
}

export interface ScanSubmitRequest {
  github_url: string
  rescan?: boolean
  /** I-3.5 — public (default) or unlisted listing posture. */
  visibility?: Visibility
}

export interface ScanSubmitResponse {
  id: string
  status: 'pending' | 'running' | 'completed' | 'failed'
  cached: boolean
  rubric_version: string
  submitted_at: string
  /** Present only when visibility='unlisted' — never logged. */
  share_url?: string | null
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

// ============================================================================
// I-3.5 — direct upload + unlisted (capability-URL) lifecycle.
// Types mirror PR1's Pydantic DTOs (services/api/app/schemas/*) — the repo's
// established hand-written-wire-type pattern (the openapi→TS generator emits
// nothing consumable here). snake_case keys per naming-conventions.md.
// ============================================================================

/** 202 body of POST /api/v1/scans/upload. */
export interface ScanUploadResponse {
  id: string
  status: 'pending' | 'running' | 'completed' | 'failed'
  source_kind: 'upload'
  visibility: Visibility
  /** Omitted for multi-capability uploads — the FE lands on the run report. */
  slug?: string | null
  /** Unlisted only — never logged. */
  share_url?: string | null
}

export interface PromotedItem {
  slug: string
  kind: string
  display_name: string
  merged: boolean
}

/** 200 body of POST /api/v1/scans/r/{token}/promote (never a 301 — D-UP-31). */
export interface PromoteRunResponse {
  promoted: boolean
  run_id: string
  visibility: 'public'
  items: PromotedItem[]
}

/** Structured upload-rejection so the DropZone can render the right bucketed copy. */
export class UploadError extends Error {
  constructor(
    public code: string,
    public httpStatus: number,
    public reason?: string
  ) {
    super(code)
    this.name = 'UploadError'
  }
}

function mapUploadError(xhr: XMLHttpRequest): UploadError {
  let code = 'upload_failed'
  let reason: string | undefined
  try {
    const detail = JSON.parse(xhr.responseText)?.detail
    if (detail && typeof detail === 'object') {
      code = typeof detail.error === 'string' ? detail.error : code
      reason = typeof detail.reason === 'string' ? detail.reason : undefined
    } else if (typeof detail === 'string') {
      code = detail
    }
  } catch {
    /* non-JSON body */
  }
  if (xhr.status === 429) code = 'rate_limit_exceeded'
  else if (xhr.status === 413 && code === 'upload_failed') code = 'upload_too_large'
  return new UploadError(code, xhr.status, reason)
}

/**
 * POST /api/v1/scans/upload (multipart). Uses XMLHttpRequest for upload-progress
 * events. Buckets: 413 upload_too_large · 415 unsupported_type|binary_not_allowed
 * · 422 archive_rejected (+reason) · 429 rate_limit_exceeded.
 */
export function submitUpload(
  file: File,
  opts: { visibility: Visibility; kind?: string },
  onProgress?: (loaded: number, total: number) => void
): Promise<ScanUploadResponse> {
  return new Promise((resolve, reject) => {
    const form = new FormData()
    form.append('file', file)
    form.append('visibility', opts.visibility)
    if (opts.kind) form.append('kind', opts.kind)

    const xhr = new XMLHttpRequest()
    xhr.open('POST', `${env.PUBLIC_API_URL}/api/v1/scans/upload`)
    xhr.responseType = 'text'
    if (onProgress) {
      xhr.upload.onprogress = (e) => {
        if (e.lengthComputable) onProgress(e.loaded, e.total)
      }
    }
    xhr.onload = () => {
      if (xhr.status === 202 || xhr.status === 200) {
        try {
          resolve(JSON.parse(xhr.responseText) as ScanUploadResponse)
        } catch {
          reject(new UploadError('bad_response', xhr.status))
        }
        return
      }
      reject(mapUploadError(xhr))
    }
    xhr.onerror = () => reject(new UploadError('network_error', 0))
    xhr.send(form)
  })
}

export type UnlistedReportResult =
  | { status: 'ok'; report: ScanRunReportDetail }
  /** A promoted run — caller should redirect to the public run report. */
  | { status: 'promoted'; runReportPath: string }
  | { status: 'not_found' }

/**
 * GET /api/v1/scans/r/{token}. A promoted run answers 307 → the public run
 * report; we read the Location with redirect:'manual' and hand back a webapp
 * path so SSR doesn't silently follow the redirect to the API origin (P0-12).
 * Invalid/expired/deleted → generic not_found (no oracle).
 */
export async function fetchUnlistedReport(token: string): Promise<UnlistedReportResult> {
  const res = await fetch(`${env.PUBLIC_API_URL}/api/v1/scans/r/${encodeURIComponent(token)}`, {
    headers: { Accept: 'application/json' },
    redirect: 'manual',
  })
  if (res.status === 307 || res.status === 308 || res.type === 'opaqueredirect') {
    const loc = res.headers.get('Location') ?? ''
    const runId = loc.match(/\/runs\/([^/?#]+)/)?.[1]
    return { status: 'promoted', runReportPath: runId ? `/scans/${runId}` : '/' }
  }
  if (res.status === 404) return { status: 'not_found' }
  if (!res.ok) throw new Error(`API ${res.status}`)
  return { status: 'ok', report: (await res.json()) as ScanRunReportDetail }
}

/** POST /api/v1/scans/r/{token}/promote — 200 structured (never 301). */
export async function promoteUnlisted(token: string): Promise<PromoteRunResponse> {
  const res = await fetch(
    `${env.PUBLIC_API_URL}/api/v1/scans/r/${encodeURIComponent(token)}/promote`,
    { method: 'POST', headers: { Accept: 'application/json' } }
  )
  if (res.status === 404) throw new Error('not_found')
  if (!res.ok) throw new Error(`API ${res.status}`)
  return (await res.json()) as PromoteRunResponse
}

/** DELETE /api/v1/scans/r/{token} — eager self-delete (token → generic 404 after). */
export async function deleteUnlisted(token: string): Promise<void> {
  const res = await fetch(`${env.PUBLIC_API_URL}/api/v1/scans/r/${encodeURIComponent(token)}`, {
    method: 'DELETE',
    headers: { Accept: 'application/json' },
  })
  if (res.status === 404) return
  if (!res.ok) throw new Error(`API ${res.status}`)
}
