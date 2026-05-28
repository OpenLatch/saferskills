import { useEffect, useState } from 'react'

import { track } from '@/lib/analytics'
import { type CatalogFacets, fetchCatalogFacets } from '@/lib/api/items'

const KIND_OPTIONS: {
  value: 'skill' | 'mcp_server' | 'hook' | 'plugin' | 'rules'
  label: string
}[] = [
  { value: 'skill', label: 'Skill' },
  { value: 'mcp_server', label: 'MCP server' },
  { value: 'hook', label: 'Hook' },
  { value: 'plugin', label: 'Plugin' },
  { value: 'rules', label: 'Rules' },
]

const SCAN_TIER_OPTIONS: { value: 'green' | 'yellow' | 'orange' | 'red'; label: string }[] = [
  { value: 'green', label: 'Green ≥80' },
  { value: 'yellow', label: 'Yellow 60-79' },
  { value: 'orange', label: 'Orange 40-59' },
  { value: 'red', label: 'Red 0-39' },
]

interface FilterState {
  kind: string[]
  scoreMin: number
  scoreMax: number
  scanTier: string[]
}

interface Props {
  initial: FilterState
}

function applyFilter(
  filterType: 'type' | 'scan_tier' | 'score_range',
  action: 'add' | 'remove',
  state: FilterState
) {
  track('catalog_filter_changed', { filter_type: filterType, action })
  const url = new URL(window.location.href)
  url.searchParams.delete('kind')
  for (const k of state.kind) url.searchParams.append('kind', k)
  url.searchParams.delete('scan_tier')
  for (const t of state.scanTier) url.searchParams.append('scan_tier', t)
  url.searchParams.set('score_min', String(state.scoreMin))
  url.searchParams.set('score_max', String(state.scoreMax))
  url.searchParams.delete('cursor')
  window.location.href = url.toString()
}

export default function CatalogFilterSide({ initial }: Props) {
  const [state, setState] = useState<FilterState>(initial)
  const [facets, setFacets] = useState<CatalogFacets | null>(null)

  useEffect(() => {
    fetchCatalogFacets()
      .then(setFacets)
      .catch(() => setFacets(null))
  }, [])

  function toggleKind(value: string) {
    const has = state.kind.includes(value)
    const next: FilterState = {
      ...state,
      kind: has ? state.kind.filter((k) => k !== value) : [...state.kind, value],
    }
    setState(next)
    applyFilter('type', has ? 'remove' : 'add', next)
  }

  function toggleTier(value: string) {
    const has = state.scanTier.includes(value)
    const next: FilterState = {
      ...state,
      scanTier: has ? state.scanTier.filter((t) => t !== value) : [...state.scanTier, value],
    }
    setState(next)
    applyFilter('scan_tier', has ? 'remove' : 'add', next)
  }

  function clearAll() {
    track('catalog_filter_changed', { filter_type: 'type', action: 'remove' })
    window.location.href = '/catalog'
  }

  return (
    <aside className="cat-side" aria-label="Catalog filters">
      <div className="cat-side-group">
        <h3 className="eyebrow eyebrow-rule">TYPE</h3>
        <ul>
          {KIND_OPTIONS.map((opt) => (
            <li key={opt.value}>
              <label>
                <input
                  type="checkbox"
                  checked={state.kind.includes(opt.value)}
                  onChange={() => toggleKind(opt.value)}
                />
                <span>{opt.label}</span>
                {facets ? (
                  <span className="cat-side-count">({facets.kind[opt.value] ?? 0})</span>
                ) : null}
              </label>
            </li>
          ))}
        </ul>
      </div>
      <div className="cat-side-group">
        <h3 className="eyebrow eyebrow-rule">SCAN TIER</h3>
        <ul>
          {SCAN_TIER_OPTIONS.map((opt) => (
            <li key={opt.value}>
              <label>
                <input
                  type="checkbox"
                  checked={state.scanTier.includes(opt.value)}
                  onChange={() => toggleTier(opt.value)}
                />
                <span>{opt.label}</span>
                {facets ? (
                  <span className="cat-side-count">({facets.tier[opt.value] ?? 0})</span>
                ) : null}
              </label>
            </li>
          ))}
        </ul>
      </div>
      <button type="button" className="cat-side-clear" onClick={clearAll}>
        Clear all filters
      </button>
    </aside>
  )
}
