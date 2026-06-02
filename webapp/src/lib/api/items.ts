import { env } from '@/env'
import type { ScanReportDetail } from '@/lib/api/scans'

export type CatalogKind = 'skill' | 'mcp_server' | 'hook' | 'plugin' | 'rules'
export type ScanTier = 'green' | 'yellow' | 'orange' | 'red' | 'unscoped'
export type ArtifactSource = 'github' | 'upload'

export interface CatalogItemSummary {
  id: string
  slug: string
  kind: CatalogKind
  display_name: string
  description?: string | null
  github_url?: string | null
  github_org: string
  github_repo: string
  /** Provenance of the scanned bytes — drives the catalog UPLOAD badge. */
  source_kind: ArtifactSource
  popularity_tier: string
  popularity_score: number
  latest_scan_score?: number | null
  latest_scan_tier?: ScanTier | null
  latest_scan_at?: string | null
  findings_count: number
  registries: string[]
  agent_compatibility: string[]
  updated_at: string
}

export interface CatalogItemDetail extends CatalogItemSummary {
  sources: Record<string, unknown>[]
  item_metadata?: Record<string, unknown> | null
}

export interface CatalogListResponse {
  data: CatalogItemSummary[]
  next_cursor: string | null
  total_count: number
  page: number
  total_pages: number
  page_size: number
}

export interface ScanHistoryPoint {
  scanned_at: string
  aggregate_score: number
  tier: ScanTier
}

export interface AgentShare {
  agent: string
  percentage: number
}

export interface InstallActivity {
  this_week: number
  this_month: number
  all_time: number
  agent_distribution: AgentShare[]
}

export interface RelatedItem {
  slug: string
  display_name: string
  aggregate_score?: number | null
  tier?: ScanTier | null
}

export interface VendorResponsePublic {
  id: string
  author: string
  body_markdown: string
  submitted_at: string
  version: number
}

export interface VersionPoint {
  tag: string | null
  scan_id: string
  /** Null for uploads — no git ref (no synthetic sentinel). */
  ref_sha: string | null
  scanned_at: string
  aggregate_score: number
  tier: ScanTier
  sub_scores: Record<string, number>
  has_snapshot: boolean
}

export type DiffLineType = 'add' | 'del' | 'ctx'
export type DiffFileStatus = 'added' | 'removed' | 'modified' | 'binary'

export interface DiffLine {
  type: DiffLineType
  text: string
  gutter: string
}

export interface DiffHunk {
  header: string
  lines: DiffLine[]
}

export interface DiffFile {
  path: string
  status: DiffFileStatus
  hunks: DiffHunk[]
  note?: string | null
}

export interface DiffResponse {
  from_scan_id: string
  to_scan_id: string
  files: DiffFile[]
  truncated: boolean
}

export interface DownloadInfo {
  scan_id: string
  byte_size: number
}

export interface RepoMeta {
  stars: number | null
  forks: number | null
  license_spdx: string | null
  latest_version: string | null
  verified: boolean
}

export interface ManifestSource {
  path: string
  content: string
  bytes: number
}

export interface ItemDetailResponse {
  item: CatalogItemDetail
  latest_scan: ScanReportDetail | null
  scan_history: ScanHistoryPoint[]
  install_activity: InstallActivity
  related_items: RelatedItem[]
  vendor_responses: VendorResponsePublic[]
  previous_sub_scores?: Record<string, number> | null
  repo: RepoMeta
  versions: VersionPoint[]
  manifest?: ManifestSource | null
  download?: DownloadInfo | null
}

export interface CatalogFacets {
  kind: Record<string, number>
  popularity_tier: Record<string, number>
  tier: Record<string, number>
  registry: Record<string, number>
  agent: Record<string, number>
  /** github | upload split for the source filter (I-3.5). */
  artifact_source: Record<string, number>
  total: number
}

export type CatalogSort =
  | 'most_installed'
  | 'recent'
  | 'highest_score'
  | 'lowest_score'
  | 'most_starred'

export interface ListItemsParams {
  kind?: string[]
  agent?: string[]
  popularity_tier?: string[]
  score_min?: number
  score_max?: number
  scan_tier?: string[]
  /** github | upload provenance filter (NOT `source` — avoids the trigger enum). */
  artifact_source?: string
  q?: string
  sort?: CatalogSort
  limit?: number
  page?: number
  cursor?: string | null
}

function buildUrl(
  path: string,
  params: Record<string, string | string[] | number | undefined>
): URL {
  const url = new URL(`${env.PUBLIC_API_URL}${path}`)
  for (const [k, v] of Object.entries(params)) {
    if (v == null) continue
    if (Array.isArray(v)) {
      for (const entry of v) url.searchParams.append(k, entry)
    } else {
      url.searchParams.set(k, String(v))
    }
  }
  return url
}

export async function listCatalogItems(params: ListItemsParams = {}): Promise<CatalogListResponse> {
  const url = buildUrl('/api/v1/items', {
    kind: params.kind,
    agent: params.agent,
    popularity_tier: params.popularity_tier,
    score_min: params.score_min,
    score_max: params.score_max,
    scan_tier: params.scan_tier,
    artifact_source: params.artifact_source,
    q: params.q,
    sort: params.sort,
    limit: params.limit ?? 25,
    page: params.page,
    cursor: params.cursor ?? undefined,
  })
  const res = await fetch(url, { headers: { Accept: 'application/json' } })
  if (!res.ok) throw new Error(`API ${res.status}`)
  return (await res.json()) as CatalogListResponse
}

export async function fetchItemBySlug(slug: string): Promise<ItemDetailResponse | null> {
  const res = await fetch(`${env.PUBLIC_API_URL}/api/v1/items/${encodeURIComponent(slug)}`, {
    headers: { Accept: 'application/json' },
  })
  if (res.status === 404) return null
  if (!res.ok) throw new Error(`API ${res.status}`)
  return (await res.json()) as ItemDetailResponse
}

export async function fetchItemDiff(
  slug: string,
  toScanId: string,
  fromScanId?: string
): Promise<DiffResponse> {
  const url = buildUrl(`/api/v1/items/${encodeURIComponent(slug)}/diff`, {
    to: toScanId,
    from: fromScanId,
  })
  const res = await fetch(url, { headers: { Accept: 'application/json' } })
  if (!res.ok) throw new Error(`API ${res.status}`)
  return (await res.json()) as DiffResponse
}

export function itemDownloadUrl(slug: string, scanId?: string): string {
  const url = buildUrl(`/api/v1/items/${encodeURIComponent(slug)}/download`, { scan: scanId })
  return url.toString()
}

export async function fetchCatalogFacets(): Promise<CatalogFacets> {
  const res = await fetch(`${env.PUBLIC_API_URL}/api/v1/items/facets`, {
    headers: { Accept: 'application/json' },
  })
  if (!res.ok) throw new Error(`API ${res.status}`)
  return (await res.json()) as CatalogFacets
}
