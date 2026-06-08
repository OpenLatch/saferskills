import type { CatalogSort } from '@/lib/api/items'

export interface CatalogState {
  kind: string[]
  agent: string[]
  popularityTier: string[] // "Scan tier" group → popularity_tier param
  scanTier: string[] // "Band" group → scan_tier param (score band)
  artifactSource: string // '' (all) | 'github' | 'upload' → artifact_source param
  scoreMin: number
  scoreMax: number
  q: string
  sort: CatalogSort
  page: number
}

export const DEFAULT_STATE: CatalogState = {
  kind: [],
  agent: [],
  popularityTier: [],
  scanTier: [],
  artifactSource: '',
  scoreMin: 0,
  scoreMax: 100,
  q: '',
  sort: 'most_installed',
  page: 1,
}

// Provenance filter (I-3.5). `value=''` is "All" (no param sent).
export const SOURCE_OPTIONS: { value: string; label: string }[] = [
  { value: '', label: 'All sources' },
  { value: 'github', label: 'GitHub' },
  { value: 'upload', label: 'Upload' },
]

export const KIND_OPTIONS: { value: string; label: string }[] = [
  { value: 'skill', label: 'Skill' },
  { value: 'mcp_server', label: 'MCP server' },
  { value: 'hook', label: 'Hook' },
  { value: 'plugin', label: 'Plugin' },
  { value: 'rules', label: 'Rules' },
]

// Agent ids mirror schemas/catalog-item.schema.json::agentCompatibility.
export const AGENT_OPTIONS: { value: string; label: string }[] = [
  { value: 'claude-code', label: 'Claude Code' },
  { value: 'cursor', label: 'Cursor' },
  { value: 'codex', label: 'Codex CLI' },
  { value: 'copilot', label: 'GH Copilot' },
  { value: 'windsurf', label: 'Windsurf' },
  { value: 'cline', label: 'Cline' },
  { value: 'gemini', label: 'Gemini CLI' },
  { value: 'openclaw', label: 'OpenClaw' },
]

// "Band" group → scan_tier param. `band` is the g/y/o/r CSS suffix.
export const BAND_OPTIONS: { value: string; label: string; band: 'g' | 'y' | 'o' | 'r' }[] = [
  { value: 'green', label: '80–100 · Green', band: 'g' },
  { value: 'yellow', label: '60–79 · Yellow', band: 'y' },
  { value: 'orange', label: '40–59 · Orange', band: 'o' },
  { value: 'red', label: '0–39 · Red', band: 'r' },
]

// "Scan tier" group → popularity_tier param.
export const SCAN_TIER_OPTIONS: { value: string; label: string }[] = [
  { value: 'deep', label: 'Deep-scanned' },
  { value: 'lite', label: 'Lite-scanned' },
  { value: 'indexed', label: 'Indexed only' },
]

export const SORT_OPTIONS: { value: CatalogSort; label: string }[] = [
  { value: 'most_installed', label: 'Most installed' },
  { value: 'recent', label: 'Recently updated' },
  { value: 'highest_score', label: 'Highest score' },
  { value: 'lowest_score', label: 'Lowest score' },
  { value: 'most_starred', label: 'Most starred' },
]

const KIND_LABEL: Record<string, string> = {
  skill: 'Skill',
  mcp_server: 'MCP',
  hook: 'Hook',
  plugin: 'Plugin',
  rules: 'Rules',
}

export function kindTag(kind: string): string {
  return KIND_LABEL[kind] ?? kind.toUpperCase()
}

export function sortLabel(sort: CatalogSort): string {
  return SORT_OPTIONS.find((o) => o.value === sort)?.label ?? 'Most installed'
}

/** Map a 0-100 score to the g/y/o/r band suffix used for dots + the left stripe. */
export function bandOf(score: number | null | undefined): 'g' | 'y' | 'o' | 'r' {
  if (score == null) return 'r'
  if (score >= 80) return 'g'
  if (score >= 60) return 'y'
  if (score >= 40) return 'o'
  return 'r'
}

const TIER_TO_BAND: Record<string, 'g' | 'y' | 'o' | 'r'> = {
  green: 'g',
  yellow: 'y',
  orange: 'o',
  red: 'r',
}

/** Prefer the scan tier; fall back to deriving a band from the score. */
export function bandFromTier(
  tier: string | null | undefined,
  score: number | null | undefined
): 'g' | 'y' | 'o' | 'r' | null {
  if (tier && tier in TIER_TO_BAND) return TIER_TO_BAND[tier]
  if (tier === 'unscoped') return null
  if (score == null) return null
  return bandOf(score)
}

/** Compact relative age — "4h", "2d", "3w", "5mo", "1y". */
export function relativeAge(iso: string | null | undefined): string {
  if (!iso) return '—'
  const then = new Date(iso).getTime()
  if (Number.isNaN(then)) return '—'
  const secs = Math.max(0, (Date.now() - then) / 1000)
  if (secs < 3600) return `${Math.max(1, Math.round(secs / 60))}m`
  if (secs < 86400) return `${Math.round(secs / 3600)}h`
  if (secs < 86400 * 14) return `${Math.round(secs / 86400)}d`
  if (secs < 86400 * 60) return `${Math.round(secs / (86400 * 7))}w`
  if (secs < 86400 * 365) return `${Math.round(secs / (86400 * 30))}mo`
  return `${Math.round(secs / (86400 * 365))}y`
}

/** Serialize catalog state to URL search params (omitting defaults). */
export function stateToSearchParams(s: CatalogState): URLSearchParams {
  const p = new URLSearchParams()
  for (const k of s.kind) p.append('kind', k)
  for (const a of s.agent) p.append('agent', a)
  for (const t of s.scanTier) p.append('scan_tier', t)
  for (const pt of s.popularityTier) p.append('popularity_tier', pt)
  if (s.artifactSource) p.set('artifact_source', s.artifactSource)
  if (s.scoreMin > 0) p.set('score_min', String(s.scoreMin))
  if (s.scoreMax < 100) p.set('score_max', String(s.scoreMax))
  if (s.q.trim()) p.set('q', s.q.trim())
  if (s.sort !== 'most_installed') p.set('sort', s.sort)
  if (s.page > 1) p.set('page', String(s.page))
  return p
}

// Every sort the clickable column headers can produce — the URL-validation
// allowlist (`stateFromSearchParams`). Kept explicit (not derived from the
// legacy SORT_OPTIONS dropdown list) so each bidirectional header sort round-trips.
const SORT_VALUES: CatalogSort[] = [
  'most_installed',
  'least_installed',
  'recent',
  'oldest',
  'highest_score',
  'lowest_score',
  'most_starred',
  'name_asc',
  'name_desc',
  'description_asc',
  'description_desc',
  'most_active',
  'least_active',
]

/** Parse catalog state from URL search params (the SSR + popstate source). */
export function stateFromSearchParams(params: URLSearchParams): CatalogState {
  const num = (key: string, fallback: number) => {
    const raw = params.get(key)
    const n = raw == null ? Number.NaN : Number.parseInt(raw, 10)
    return Number.isNaN(n) ? fallback : Math.min(100, Math.max(0, n))
  }
  const sortRaw = params.get('sort') as CatalogSort | null
  const pageRaw = Number.parseInt(params.get('page') ?? '1', 10)
  const sourceRaw = params.get('artifact_source') ?? ''
  return {
    kind: params.getAll('kind'),
    agent: params.getAll('agent'),
    popularityTier: params.getAll('popularity_tier'),
    scanTier: params.getAll('scan_tier'),
    artifactSource: sourceRaw === 'github' || sourceRaw === 'upload' ? sourceRaw : '',
    scoreMin: num('score_min', 0),
    scoreMax: num('score_max', 100),
    q: params.get('q') ?? '',
    sort: sortRaw && SORT_VALUES.includes(sortRaw) ? sortRaw : 'most_installed',
    page: Number.isNaN(pageRaw) || pageRaw < 1 ? 1 : pageRaw,
  }
}
