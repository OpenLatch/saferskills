import { env } from '@/env'

export type CatalogKind = 'skill' | 'mcp_server' | 'hook' | 'plugin' | 'rules'
export type ScanTier = 'green' | 'yellow' | 'orange' | 'red' | 'unscoped'

export interface CatalogItemSummary {
  id: string
  slug: string
  kind: CatalogKind
  display_name: string
  description?: string | null
  github_url?: string | null
  github_org: string
  github_repo: string
  popularity_tier: string
  popularity_score: number
  latest_scan_score?: number | null
  latest_scan_tier?: ScanTier | null
  latest_scan_at?: string | null
  findings_count: number
  registries: string[]
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
}

export interface CatalogFacets {
  kind: Record<string, number>
  popularity_tier: Record<string, number>
  tier: Record<string, number>
  registry: Record<string, number>
  total: number
}

export interface ListItemsParams {
  kind?: string[]
  score_min?: number
  score_max?: number
  scan_tier?: string[]
  q?: string
  sort?: 'most_installed' | 'recent' | 'highest_score' | 'lowest_score' | 'most_starred'
  limit?: number
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
    score_min: params.score_min,
    score_max: params.score_max,
    scan_tier: params.scan_tier,
    q: params.q,
    sort: params.sort,
    limit: params.limit ?? 25,
    cursor: params.cursor ?? undefined,
  })
  const res = await fetch(url, { headers: { Accept: 'application/json' } })
  if (!res.ok) throw new Error(`API ${res.status}`)
  return (await res.json()) as CatalogListResponse
}

export async function getCatalogItem(slug: string): Promise<CatalogItemDetail> {
  const res = await fetch(`${env.PUBLIC_API_URL}/api/v1/items/${encodeURIComponent(slug)}`, {
    headers: { Accept: 'application/json' },
  })
  if (!res.ok) throw new Error(`API ${res.status}`)
  return (await res.json()) as CatalogItemDetail
}

export async function fetchCatalogFacets(): Promise<CatalogFacets> {
  const res = await fetch(`${env.PUBLIC_API_URL}/api/v1/items/facets`, {
    headers: { Accept: 'application/json' },
  })
  if (!res.ok) throw new Error(`API ${res.status}`)
  return (await res.json()) as CatalogFacets
}
