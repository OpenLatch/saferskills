import { useCallback, useEffect, useRef, useState } from 'react'

import { track } from '@/lib/analytics'
import {
  type CatalogFacets,
  type CatalogItemSummary,
  type CatalogListResponse,
  type CatalogSort,
  fetchCatalogFacets,
  listCatalogItems,
} from '@/lib/api/items'
import CatalogFilterSide from './CatalogFilterSide'
import CatalogResultsList from './CatalogResultsList'
import CatalogToolbar from './CatalogToolbar'
import {
  type CatalogState,
  DEFAULT_STATE,
  stateFromSearchParams,
  stateToSearchParams,
} from './constants'

const PAGE_SIZE = 25

type ToggleGroup = 'kind' | 'agent' | 'scanTier' | 'popularityTier'

const GROUP_TO_STATE_KEY: Record<ToggleGroup, keyof CatalogState> = {
  kind: 'kind',
  agent: 'agent',
  scanTier: 'scanTier',
  popularityTier: 'popularityTier',
}

const GROUP_TO_EVENT: Record<ToggleGroup, 'type' | 'agent' | 'scan_tier'> = {
  kind: 'type',
  agent: 'agent',
  scanTier: 'scan_tier',
  popularityTier: 'scan_tier',
}

interface Props {
  initialState: CatalogState
  initialData: CatalogListResponse
  initialFacets: CatalogFacets | null
  totalIndexed: number
  registriesCount: number
}

function paramsFor(state: CatalogState) {
  return {
    kind: state.kind,
    agent: state.agent,
    popularity_tier: state.popularityTier,
    scan_tier: state.scanTier,
    score_min: state.scoreMin,
    score_max: state.scoreMax,
    q: state.q.trim() || undefined,
    sort: state.sort,
    page: state.page,
    limit: PAGE_SIZE,
  }
}

export default function CatalogApp({
  initialState,
  initialData,
  initialFacets,
  totalIndexed,
  registriesCount,
}: Props) {
  const [state, setState] = useState<CatalogState>(initialState)
  const [items, setItems] = useState<CatalogItemSummary[]>(initialData.data)
  const [totalCount, setTotalCount] = useState(initialData.total_count)
  const [totalPages, setTotalPages] = useState(initialData.total_pages)
  const [facets, setFacets] = useState<CatalogFacets | null>(initialFacets)
  const [loading, setLoading] = useState(false)

  const searchRef = useRef<HTMLInputElement>(null)
  const reqToken = useRef(0)
  const debounceTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  const runQuery = useCallback(async (next: CatalogState, push: boolean) => {
    const token = ++reqToken.current
    if (push) {
      const qs = stateToSearchParams(next).toString()
      window.history.pushState(null, '', qs ? `/catalog?${qs}` : '/catalog')
    }
    setLoading(true)
    try {
      const res = await listCatalogItems(paramsFor(next))
      if (token !== reqToken.current) return // a newer request superseded this one
      setItems(res.data)
      setTotalCount(res.total_count)
      setTotalPages(res.total_pages)
    } catch {
      if (token !== reqToken.current) return
      setItems([])
      setTotalCount(0)
      setTotalPages(1)
    } finally {
      if (token === reqToken.current) setLoading(false)
    }
  }, [])

  // Commit a new state: update immediately, then fetch + push URL (optionally debounced).
  const commit = useCallback(
    (next: CatalogState, opts: { debounce?: boolean } = {}) => {
      setState(next)
      if (debounceTimer.current) clearTimeout(debounceTimer.current)
      if (opts.debounce) {
        debounceTimer.current = setTimeout(() => runQuery(next, true), 350)
      } else {
        runQuery(next, true)
      }
    },
    [runQuery]
  )

  // Fetch facets if SSR didn't provide them.
  useEffect(() => {
    if (facets) return
    fetchCatalogFacets()
      .then(setFacets)
      .catch(() => setFacets(null))
  }, [facets])

  // Back/forward: re-derive state from the URL and refetch without pushing.
  useEffect(() => {
    function onPop() {
      const next = stateFromSearchParams(new URLSearchParams(window.location.search))
      setState(next)
      runQuery(next, false)
    }
    window.addEventListener('popstate', onPop)
    return () => window.removeEventListener('popstate', onPop)
  }, [runQuery])

  // ⌘K focuses search; ⌘G jumps to a page.
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (!(e.metaKey || e.ctrlKey)) return
      const key = e.key.toLowerCase()
      if (key === 'k') {
        e.preventDefault()
        searchRef.current?.focus()
        searchRef.current?.select()
      } else if (key === 'g') {
        e.preventDefault()
        const raw = window.prompt(`Jump to page (1–${totalPages})`)
        if (raw == null) return
        const n = Number.parseInt(raw, 10)
        if (Number.isNaN(n)) return
        const clamped = Math.min(totalPages, Math.max(1, n))
        commit({ ...state, page: clamped })
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [state, totalPages, commit])

  const onToggle = useCallback(
    (group: ToggleGroup, value: string) => {
      const key = GROUP_TO_STATE_KEY[group]
      const current = state[key] as string[]
      const has = current.includes(value)
      const nextArr = has ? current.filter((v) => v !== value) : [...current, value]
      track('catalog_filter_changed', {
        filter_type: GROUP_TO_EVENT[group],
        action: has ? 'remove' : 'add',
      })
      commit({ ...state, [key]: nextArr, page: 1 })
    },
    [state, commit]
  )

  const onScore = useCallback(
    (min: number, max: number) => {
      track('catalog_filter_changed', { filter_type: 'score_range', action: 'add' })
      commit({ ...state, scoreMin: min, scoreMax: max, page: 1 }, { debounce: true })
    },
    [state, commit]
  )

  const onQueryChange = useCallback(
    (q: string) => commit({ ...state, q, page: 1 }, { debounce: true }),
    [state, commit]
  )

  const onSearchSubmit = useCallback(() => {
    if (debounceTimer.current) clearTimeout(debounceTimer.current)
    runQuery({ ...state, page: 1 }, true)
    setState((s) => ({ ...s, page: 1 }))
  }, [state, runQuery])

  const onSortChange = useCallback(
    (sort: CatalogSort) => {
      track('catalog_filter_changed', { filter_type: 'recency', action: 'add' })
      commit({ ...state, sort, page: 1 })
    },
    [state, commit]
  )

  const onPageChange = useCallback(
    (page: number) => {
      commit({ ...state, page })
      if (typeof document !== 'undefined') {
        document.querySelector('.cat-split')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
      }
    },
    [state, commit]
  )

  const onClear = useCallback(() => {
    track('catalog_filter_changed', { filter_type: 'type', action: 'remove' })
    commit({ ...DEFAULT_STATE })
  }, [commit])

  const onItemClick = useCallback((item: CatalogItemSummary) => {
    track('catalog_item_clicked', {
      tier: (item.latest_scan_tier ?? 'unscoped') as
        | 'green'
        | 'yellow'
        | 'orange'
        | 'red'
        | 'unscoped',
      kind: item.kind,
    })
  }, [])

  const emptyVariant: 'empty-catalog' | 'no-match' = totalCount === 0 ? 'empty-catalog' : 'no-match'

  return (
    <>
      <CatalogToolbar
        ref={searchRef}
        query={state.q}
        totalIndexed={totalIndexed}
        registriesCount={registriesCount}
        onQueryChange={onQueryChange}
        onSubmit={onSearchSubmit}
      />
      <div className="cat-split">
        <CatalogFilterSide
          state={state}
          facets={facets}
          onToggle={onToggle}
          onScore={onScore}
          onClear={onClear}
        />
        <CatalogResultsList
          items={items}
          page={state.page}
          pageSize={PAGE_SIZE}
          totalCount={totalCount}
          totalPages={totalPages}
          sort={state.sort}
          loading={loading}
          emptyVariant={items.length === 0 ? emptyVariant : undefined}
          onSortChange={onSortChange}
          onPageChange={onPageChange}
          onItemClick={onItemClick}
        />
      </div>
    </>
  )
}
