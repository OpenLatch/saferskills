/**
 * `/agents` directory filter ↔ URL-param mapping (I-5.6 §12, D-5.6-09).
 *
 * Mirrors `catalog/constants.ts` — the page SSR-derives the initial filter state
 * from the request URL, the island re-derives on popstate, and both build the
 * `AgentListParams` the data layer sends. Latest-first (`newest`) is the default
 * sort (the leaderboard-avoiding order).
 */
import {
  type AgentFilters,
  type AgentSortKey,
  DEFAULT_AGENT_FILTERS,
} from '@ui/components/molecules/AgentFilterBar'

import type { AgentListParams } from '@/lib/api/agent-scans'

const SORTS: AgentSortKey[] = ['newest', 'score_asc', 'score_desc']

function clampScore(raw: string | null, fallback: number): number {
  if (raw === null) return fallback
  const n = Number.parseInt(raw, 10)
  if (Number.isNaN(n)) return fallback
  return Math.max(0, Math.min(100, n))
}

function asSort(raw: string | null): AgentSortKey {
  return (SORTS as string[]).includes(raw ?? '') ? (raw as AgentSortKey) : 'newest'
}

export function filtersFromSearchParams(sp: URLSearchParams): AgentFilters {
  return {
    q: sp.get('q') ?? '',
    scoreMin: clampScore(sp.get('score_min'), 0),
    scoreMax: clampScore(sp.get('score_max'), 100),
    period: sp.getAll('period'),
    runtime: sp.getAll('runtime'),
    severity: sp.getAll('severity'),
    sort: asSort(sp.get('sort')),
  }
}

export function filtersToSearchParams(f: AgentFilters): URLSearchParams {
  const sp = new URLSearchParams()
  const q = f.q.trim()
  if (q) sp.set('q', q)
  if (f.scoreMin > 0) sp.set('score_min', String(f.scoreMin))
  if (f.scoreMax < 100) sp.set('score_max', String(f.scoreMax))
  for (const v of f.period) sp.append('period', v)
  for (const v of f.runtime) sp.append('runtime', v)
  for (const v of f.severity) sp.append('severity', v)
  if (f.sort !== 'newest') sp.set('sort', f.sort)
  return sp
}

/** Build the API list params from the filter state for a given 1-based page. */
export function filtersToParams(f: AgentFilters, page: number, pageSize: number): AgentListParams {
  return {
    scoreMin: f.scoreMin > 0 ? f.scoreMin : undefined,
    scoreMax: f.scoreMax < 100 ? f.scoreMax : undefined,
    period: f.period,
    runtime: f.runtime,
    severity: f.severity,
    sort: f.sort,
    page,
    pageSize,
  }
}

/** Is the filter state the untouched default (drives the empty-state copy)? */
export function isDefaultFilters(f: AgentFilters): boolean {
  return (
    f.q.trim() === '' &&
    f.scoreMin === DEFAULT_AGENT_FILTERS.scoreMin &&
    f.scoreMax === DEFAULT_AGENT_FILTERS.scoreMax &&
    f.period.length === 0 &&
    f.runtime.length === 0 &&
    f.severity.length === 0
  )
}
