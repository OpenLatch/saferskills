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
  /** Behavioral tests in the active pack (AS-NN count) — the collecting-state
   *  methodology instrument's "tests, every scan" cell. Build-time constant. */
  packTestCount: number
  /** Epoch ms captured once by the page render — drives the relative card times
   *  (SSR + hydration agree, mirrors the mockup `NOW`). */
  now: number
}

/** The mockup's 6-card loading skeleton (bar layout per `.sk-card`). */
function SkeletonCard() {
  return (
    <div className="sk-card" aria-hidden="true">
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10 }}>
        <div className="sk-bar" style={{ width: '50%' }} />
        <div className="sk-bar sm" style={{ width: '22%' }} />
      </div>
      <div className="sk-bar tall" style={{ width: '40%' }} />
      <div style={{ display: 'flex', gap: 6 }}>
        <div className="sk-bar sm" style={{ width: '20%' }} />
        <div className="sk-bar sm" style={{ width: '20%' }} />
        <div className="sk-bar sm" style={{ width: '20%' }} />
      </div>
      <div className="sk-bar sm" style={{ width: '60%', marginTop: 'auto' }} />
    </div>
  )
}

export default function AgentDirectoryApp({
  initialFilters,
  initialData,
  initialStats,
  packTestCount,
  now,
}: Props) {
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
  const q = filters.q.trim()

  // Below the publish gate the corpus rate (and the band thermometer beside it) is
  // premature, so the header drops to a single full-width methodology instrument; at
  // or above the gate it's the published rate + the risk thermometer (mockup layout).
  const published = initialStats.gate_met && initialStats.pct_with_critical !== null
  const meter = (
    <CorpusRiskMeter
      pctWithCritical={initialStats.pct_with_critical}
      gateMet={initialStats.gate_met}
      corpusCount={initialStats.corpus_count}
      gateTarget={initialStats.gate_target}
      packTestCount={packTestCount}
    />
  )

  return (
    <>
      <header className="obs-head">
        <div className="container">
          <span className="obs-eyebrow">
            {published ? (
              'Agents · the public corpus'
            ) : (
              <span>
                The public corpus ·{' '}
                <span className="obs-live">
                  <i aria-hidden="true" /> live
                </span>
              </span>
            )}
          </span>
          {published ? (
            <div className="obs-grid">
              {meter}
              <RiskThermometer
                distribution={initialStats.band_distribution}
                windowLabel={initialStats.window_label}
                corpusCount={initialStats.corpus_count}
              />
            </div>
          ) : (
            meter
          )}
        </div>
      </header>

      <AgentFilterBar value={filters} onChange={onFilterChange} />

      <div className="obs-body">
        <div className="container">
          {loading ? (
            <div
              className="obs-skeleton"
              role="status"
              aria-busy="true"
              aria-label="Loading agents"
            >
              {SKELETON_KEYS.map((k) => (
                <SkeletonCard key={k} />
              ))}
            </div>
          ) : isEmpty ? (
            <div className="obs-empty">
              <div className="ee-glyph" aria-hidden="true">
                <svg
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.6"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  aria-hidden="true"
                >
                  <circle cx="11" cy="11" r="7" />
                  <path d="m20 20-3.5-3.5" />
                </svg>
              </div>
              <h3>No agents match</h3>
              <p>
                Nothing in the index matches{' '}
                <span className="ee-q">{q ? `“${q}”` : 'your filters'}</span>. Try widening the
                score range, clearing the date, or scanning the agent yourself.
              </p>
              {!isDefaultFilters(filters) && (
                <button type="button" className="ee-clear" onClick={onClear}>
                  Clear all filters
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
                    now={now}
                    capabilityTally={it.capability_tally}
                    findings={it.findings_summary}
                    href={`/agents/${it.id}`}
                    isNewest={newestIsLive && i === 0}
                  />
                ))}
              </div>

              {hasMore ? (
                <>
                  <div className="obs-more">
                    <span className="sp" aria-hidden="true" />
                    <span>Loading more agents…</span>
                  </div>
                  <div ref={sentinelRef} className="obs-sentinel" />
                </>
              ) : (
                items.length > 0 && (
                  <div className="obs-more done">
                    <span>All {total.toLocaleString()} matching agents shown</span>
                  </div>
                )
              )}
            </>
          )}
        </div>
      </div>

      <div className="obs-ridge">
        <RidgeStars label="— END OF INDEX —" />
      </div>
    </>
  )
}
