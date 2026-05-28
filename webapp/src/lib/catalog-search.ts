import mock from '@/data/catalog-mock.json'

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

const ALL: readonly CatalogHit[] = (mock.data as CatalogHit[]) ?? []

const GROUP_ORDER: readonly CatalogKind[] = ['skill', 'mcp_server', 'hook', 'plugin', 'rules']

const MAX_PER_GROUP = 8

/**
 * Substring-match the catalog by display_name. Case-insensitive.
 * Returned hits are grouped by kind in the canonical group order so the
 * dropdown can render `<Command.Group>`s without re-sorting.
 *
 * At W1 this filters the mock JSON in-memory. At W2 swap the body for a
 * `fetch('/api/v1/catalog/search?q=...', { signal })` call — the public
 * shape (`CatalogHit[]`, snake_case keys) is the locked wire contract so
 * the dropdown component does not change.
 */
export async function searchCatalog(query: string, signal?: AbortSignal): Promise<CatalogHit[]> {
  if (signal?.aborted) {
    throw new DOMException('aborted', 'AbortError')
  }
  const q = query.trim().toLowerCase()
  if (!q) return []
  return ALL.filter((item) => item.display_name.toLowerCase().includes(q))
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
