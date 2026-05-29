import type { CatalogFacets } from '@/lib/api/items'
import {
  AGENT_OPTIONS,
  BAND_OPTIONS,
  type CatalogState,
  KIND_OPTIONS,
  SCAN_TIER_OPTIONS,
} from './constants'
import ScoreRangeSlider from './ScoreRangeSlider'

interface Props {
  state: CatalogState
  facets: CatalogFacets | null
  onToggle: (group: 'kind' | 'agent' | 'scanTier' | 'popularityTier', value: string) => void
  onScore: (min: number, max: number) => void
  onClear: () => void
}

function Count({ n }: { n: number | undefined }) {
  if (n == null) return null
  return <span className="ct">{n.toLocaleString()}</span>
}

export default function CatalogFilterSide({ state, facets, onToggle, onScore, onClear }: Props) {
  return (
    <aside className="cat-side" aria-label="Catalog filters">
      <div className="grp">
        <h6>Type</h6>
        {KIND_OPTIONS.map((opt) => {
          const on = state.kind.includes(opt.value)
          return (
            <button
              type="button"
              key={opt.value}
              className={`opt${on ? ' on' : ''}`}
              aria-pressed={on}
              onClick={() => onToggle('kind', opt.value)}
            >
              <span className="box" aria-hidden="true" />
              <span>{opt.label}</span>
              <Count n={facets?.kind[opt.value]} />
            </button>
          )
        })}
      </div>

      <div className="grp">
        <h6>Agent compatibility</h6>
        {AGENT_OPTIONS.map((opt) => {
          const on = state.agent.includes(opt.value)
          return (
            <button
              type="button"
              key={opt.value}
              className={`opt${on ? ' on' : ''}`}
              aria-pressed={on}
              onClick={() => onToggle('agent', opt.value)}
            >
              <span className="box" aria-hidden="true" />
              <span>{opt.label}</span>
              <Count n={facets?.agent[opt.value]} />
            </button>
          )
        })}
      </div>

      <ScoreRangeSlider min={state.scoreMin} max={state.scoreMax} onChange={onScore} />

      <div className="grp">
        <h6>Band</h6>
        {BAND_OPTIONS.map((opt) => {
          const on = state.scanTier.includes(opt.value)
          return (
            <button
              type="button"
              key={opt.value}
              className={`opt${on ? ' on' : ''}`}
              aria-pressed={on}
              onClick={() => onToggle('scanTier', opt.value)}
            >
              <span className="box" aria-hidden="true" />
              <span className={`band-dot ${opt.band}`} aria-hidden="true" />
              <span>{opt.label}</span>
              <Count n={facets?.tier[opt.value]} />
            </button>
          )
        })}
      </div>

      <div className="grp">
        <h6>Scan tier</h6>
        {SCAN_TIER_OPTIONS.map((opt) => {
          const on = state.popularityTier.includes(opt.value)
          return (
            <button
              type="button"
              key={opt.value}
              className={`opt${on ? ' on' : ''}`}
              aria-pressed={on}
              onClick={() => onToggle('popularityTier', opt.value)}
            >
              <span className="box" aria-hidden="true" />
              <span>{opt.label}</span>
              <Count n={facets?.popularity_tier[opt.value]} />
            </button>
          )
        })}
      </div>

      <button type="button" className="clear-link" onClick={onClear}>
        Clear all filters
      </button>
    </aside>
  )
}
