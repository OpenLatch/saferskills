import RidgeStars from '@ui/components/atoms/RidgeStars'
import AgentFilterBar, { type AgentFilters } from '@ui/components/molecules/AgentFilterBar'
import CorpusRiskMeter from '@ui/components/molecules/CorpusRiskMeter'
import DossierCard from '@ui/components/molecules/DossierCard'
import RiskThermometer from '@ui/components/molecules/RiskThermometer'
import { useCallback, useEffect, useRef, useState } from 'react'

import {
  type AgentAggregateStats,
  type AgentScanListEnvelope,
  type AgentScanSummary,
  listAgentScans,
} from '@/lib/api/agent-scans'
import { filtersToParams, filtersToSearchParams, isDefaultFilters } from './directory-state'

const PAGE_SIZE = 24
// Stable keys for the 6-card loading skeleton (no array-index keys).
const SKELETON_KEYS = ['sk1', 'sk2', 'sk3', 'sk4', 'sk5', 'sk6']

interface Props {
  initialFilters: AgentFilters
  initialData: AgentScanListEnvelope
  initialStats: AgentAggregateStats
}

export default function AgentDirectoryApp({ initialFilters, initialData, initialStats }: Props) {
  const [filters, setFilters] = useState<AgentFilters>(initialFilters)
  const [items, setItems] = useState<AgentScanSummary[]>(initialData.data)
  const [total, setTotal] = useState(initialData.total_count)
  const [page, setPage] = useState(initialData.page)
  const [loading, setLoading] = useState(false)
  const [loadingMore, setLoadingMore] = useState(false)

  const reqToken = useRef(0)
  const debounceTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const sentinelRef = useRef<HTMLDivElement | null>(null)

  const hasMore = items.length < total

  // Replace the grid with page 1 for a new filter state (optionally URL-pushing).
  const runQuery = useCallback(async (next: AgentFilters, push: boolean) => {
    const token = ++reqToken.current
    if (push && typeof window !== 'undefined') {
      const qs = filtersToSearchParams(next).toString()
      window.history.pushState(null, '', qs ? `/agents?${qs}` : '/agents')
    }
    setLoading(true)
    try {
      const res = await listAgentScans(filtersToParams(next, 1, PAGE_SIZE))
      if (token !== reqToken.current) return
      setItems(res.data)
      setTotal(res.total_count)
      setPage(1)
    } catch {
      if (token !== reqToken.current) return
      setItems([])
      setTotal(0)
      setPage(1)
    } finally {
      if (token === reqToken.current) setLoading(false)
    }
  }, [])

  const commit = useCallback(
    (patch: Partial<AgentFilters>, opts: { debounce?: boolean } = {}) => {
      setFilters((prev) => {
        const next = { ...prev, ...patch }
        if (debounceTimer.current) clearTimeout(debounceTimer.current)
        if (opts.debounce) {
          debounceTimer.current = setTimeout(() => runQuery(next, true), 350)
        } else {
          runQuery(next, true)
        }
        return next
      })
    },
    [runQuery]
  )

  const onFilterChange = useCallback(
    (patch: Partial<AgentFilters>) => {
      // The free-text + slider debounce; discrete controls commit immediately.
      const debounce = 'q' in patch || 'scoreMin' in patch || 'scoreMax' in patch
      commit(patch, { debounce })
    },
    [commit]
  )

  const onClear = useCallback(() => {
    commit({
      q: '',
      scoreMin: 0,
      scoreMax: 100,
      period: [],
      runtime: [],
      severity: [],
    })
  }, [commit])

  // Infinite scroll: append the next page when the sentinel enters view.
  const loadMore = useCallback(async () => {
    if (loadingMore || loading || !hasMore) return
    // Snapshot the request token: a filter change mid-fetch bumps it (via runQuery),
    // so a stale page never gets appended onto the now-replaced grid.
    const token = reqToken.current
    const nextPage = page + 1
    setLoadingMore(true)
    try {
      const res = await listAgentScans(filtersToParams(filters, nextPage, PAGE_SIZE))
      if (token !== reqToken.current) return
      setItems((prev) => [...prev, ...res.data])
      setTotal(res.total_count)
      setPage(nextPage)
    } catch {
      /* keep what we have; the sentinel will retry on the next intersection */
    } finally {
      if (token === reqToken.current) setLoadingMore(false)
    }
  }, [loadingMore, loading, hasMore, page, filters])

  useEffect(() => {
    const el = sentinelRef.current
    if (!el || !('IntersectionObserver' in window)) return
    const io = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting)) loadMore()
      },
      { rootMargin: '400px 0px' }
    )
    io.observe(el)
    return () => io.disconnect()
  }, [loadMore])

  // Back/forward: re-derive from the URL + refetch without pushing.
  useEffect(() => {
    function onPop() {
      // Lazy import avoids a server-side `window` read at module load.
      import('./directory-state').then(({ filtersFromSearchParams }) => {
        const next = filtersFromSearchParams(new URLSearchParams(window.location.search))
        setFilters(next)
        runQuery(next, false)
      })
    }
    window.addEventListener('popstate', onPop)
    return () => window.removeEventListener('popstate', onPop)
  }, [runQuery])

  const isEmpty = !loading && items.length === 0
  const newestIsLive = filters.sort === 'newest'

  return (
    <>
      <section className="obs-head">
        <div className="container">
          <div className="obs-grid">
            <CorpusRiskMeter
              pctWithCritical={initialStats.pct_with_critical}
              gateMet={initialStats.gate_met}
              corpusCount={initialStats.corpus_count}
              gateTarget={initialStats.gate_target}
            />
            <RiskThermometer
              distribution={initialStats.band_distribution}
              windowLabel={initialStats.window_label}
              corpusCount={initialStats.corpus_count}
            />
          </div>
        </div>
      </section>

      <section className="obs-body">
        <div className="container">
          <AgentFilterBar value={filters} onChange={onFilterChange} />

          {loading ? (
            <div className="card-grid" role="status" aria-busy="true" aria-label="Loading agents">
              {SKELETON_KEYS.map((k) => (
                <div key={k} className="sk-card" aria-hidden="true" />
              ))}
            </div>
          ) : isEmpty ? (
            <div className="obs-empty">
              <span className="ee-glyph" aria-hidden="true">
                ⌕
              </span>
              <p className="ee-q">No agents match</p>
              {!isDefaultFilters(filters) && (
                <button type="button" className="ee-clear" onClick={onClear}>
                  Clear all
                </button>
              )}
            </div>
          ) : (
            <>
              <div className="card-grid">
                {items.map((it, i) => (
                  <DossierCard
                    key={it.id}
                    agentName={it.agent_name}
                    runtime={it.runtime}
                    score={it.score}
                    band={it.band}
                    scannedAt={it.scanned_at}
                    capabilityTally={it.capability_tally}
                    findings={it.findings_summary}
                    trustTier={it.trust_tier}
                    href={`/agents/${it.id}`}
                    isNewest={newestIsLive && i === 0}
                  />
                ))}
              </div>

              {hasMore ? (
                <div ref={sentinelRef} className="obs-sentinel">
                  <span className="obs-more">{loadingMore ? 'Loading more agents…' : ''}</span>
                </div>
              ) : (
                items.length > 0 && (
                  <>
                    <p className="obs-more obs-all">
                      All {total.toLocaleString()} matching agents shown
                    </p>
                    <RidgeStars label="— END OF INDEX —" />
                  </>
                )
              )}
            </>
          )}
        </div>
      </section>
    </>
  )
}
