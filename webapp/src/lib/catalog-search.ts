import { type CatalogItemSummary, listCatalogItems, type ScanTier } from '@/lib/api/items'

export type CatalogKind = 'skill' | 'mcp_server' | 'hook' | 'plugin' | 'rules'
export type Severity = 'info' | 'low' | 'medium' | 'high' | 'critical'

export interface CatalogHit {
  kind: CatalogKind
  slug: string
  display_name: string
  editor: string
  scan_score: number
  severity: Severity
}

export interface CatalogGroup {
  kind: CatalogKind
  hits: CatalogHit[]
}

const GROUP_ORDER: readonly CatalogKind[] = ['skill', 'mcp_server', 'hook', 'plugin', 'rules']

const MAX_PER_GROUP = 8

/** Number of catalog rows the typeahead pulls per keystroke (≥ 5 groups × 8). */
const SEARCH_LIMIT = 40

/** Coarse tier → severity bucket for the dropdown row's tint + label. The
 *  list API exposes the aggregate `latest_scan_tier`, not a per-finding
 *  severity, so the preview pill mirrors the score band. */
const TIER_SEVERITY: Record<ScanTier, Severity> = {
  green: 'info',
  yellow: 'low',
  orange: 'medium',
  red: 'high',
  unscoped: 'info',
}

function toHit(item: CatalogItemSummary): CatalogHit {
  return {
    kind: item.kind,
    slug: item.slug,
    display_name: item.display_name,
    editor: item.agent_compatibility[0] ?? '—',
    scan_score: item.latest_scan_score ?? 0,
    severity: TIER_SEVERITY[item.latest_scan_tier ?? 'unscoped'],
  }
}

/**
 * Search the live public catalog by query (name + full-text), returning hits
 * mapped to the dropdown's `CatalogHit` shape. Case-insensitive ranking is the
 * backend's (`GET /api/v1/items?q=`); every public query hard-filters
 * `visibility='public'`, so public uploads surface here too.
 */
export async function searchCatalog(query: string, signal?: AbortSignal): Promise<CatalogHit[]> {
  if (signal?.aborted) {
    throw new DOMException('aborted', 'AbortError')
  }
  const q = query.trim()
  if (!q) return []
  const res = await listCatalogItems({ q, limit: SEARCH_LIMIT })
  if (signal?.aborted) {
    throw new DOMException('aborted', 'AbortError')
  }
  return res.data.map(toHit)
}

/**
 * Bucket a flat hit list into kind-grouped arrays, capped at
 * MAX_PER_GROUP rows per group. Empty groups are dropped.
 */
export function groupByKind(hits: readonly CatalogHit[]): CatalogGroup[] {
  const buckets = new Map<CatalogKind, CatalogHit[]>()
  for (const hit of hits) {
    const bucket = buckets.get(hit.kind) ?? []
    if (bucket.length < MAX_PER_GROUP) {
      bucket.push(hit)
      buckets.set(hit.kind, bucket)
    }
  }
  return GROUP_ORDER.filter((kind) => buckets.has(kind)).map((kind) => ({
    kind,
    hits: buckets.get(kind) as CatalogHit[],
  }))
}

export const KIND_LABELS: Record<CatalogKind, string> = {
  skill: 'Skills',
  mcp_server: 'MCP Servers',
  hook: 'Hooks',
  plugin: 'Plugins',
  rules: 'Rules',
}
