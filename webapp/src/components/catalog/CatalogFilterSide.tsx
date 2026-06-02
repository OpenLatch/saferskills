import Checkbox from '@ui/components/atoms/Checkbox'
import RangeSlider from '@ui/components/atoms/RangeSlider'
import type { CatalogFacets } from '@/lib/api/items'
import {
  AGENT_OPTIONS,
  BAND_OPTIONS,
  type CatalogState,
  KIND_OPTIONS,
  SCAN_TIER_OPTIONS,
  SOURCE_OPTIONS,
} from './constants'

interface Props {
  state: CatalogState
  facets: CatalogFacets | null
  onToggle: (group: 'kind' | 'agent' | 'scanTier' | 'popularityTier', value: string) => void
  onSource: (value: string) => void
  onScore: (min: number, max: number) => void
  onClear: () => void
}

export default function CatalogFilterSide({
  state,
  facets,
  onToggle,
  onSource,
  onScore,
  onClear,
}: Props) {
  const sourceCount = (value: string): number | undefined => {
    if (!facets) return undefined
    if (value === '') return facets.total
    return facets.artifact_source[value]
  }
  return (
    <aside className="cat-side" aria-label="Catalog filters">
      <div className="grp">
        <h6>Source</h6>
        {SOURCE_OPTIONS.map((opt) => (
          <Checkbox
            key={opt.value || 'all'}
            variant="radio"
            block
            checked={state.artifactSource === opt.value}
            onChange={() => onSource(opt.value)}
            label={opt.label}
            count={sourceCount(opt.value)}
          />
        ))}
      </div>

      <div className="grp">
        <h6>Type</h6>
        {KIND_OPTIONS.map((opt) => (
          <Checkbox
            key={opt.value}
            block
            checked={state.kind.includes(opt.value)}
            onChange={() => onToggle('kind', opt.value)}
            label={opt.label}
            count={facets?.kind[opt.value]}
          />
        ))}
      </div>

      <div className="grp">
        <h6>Agent compatibility</h6>
        {AGENT_OPTIONS.map((opt) => (
          <Checkbox
            key={opt.value}
            block
            checked={state.agent.includes(opt.value)}
            onChange={() => onToggle('agent', opt.value)}
            label={opt.label}
            count={facets?.agent[opt.value]}
          />
        ))}
      </div>

      <div className="grp">
        <h6>Score range</h6>
        <RangeSlider
          min={state.scoreMin}
          max={state.scoreMax}
          onChange={onScore}
          minAriaLabel="Minimum score"
          maxAriaLabel="Maximum score"
        />
      </div>

      <div className="grp">
        <h6>Band</h6>
        {BAND_OPTIONS.map((opt) => (
          <Checkbox
            key={opt.value}
            block
            checked={state.scanTier.includes(opt.value)}
            onChange={() => onToggle('scanTier', opt.value)}
            label={opt.label}
            count={facets?.tier[opt.value]}
            adornment={<span className={`band-dot ${opt.band}`} aria-hidden="true" />}
          />
        ))}
      </div>

      <div className="grp">
        <h6>Scan tier</h6>
        {SCAN_TIER_OPTIONS.map((opt) => (
          <Checkbox
            key={opt.value}
            block
            checked={state.popularityTier.includes(opt.value)}
            onChange={() => onToggle('popularityTier', opt.value)}
            label={opt.label}
            count={facets?.popularity_tier[opt.value]}
          />
        ))}
      </div>

      <button type="button" className="clear-link" onClick={onClear}>
        Clear all filters
      </button>
    </aside>
  )
}
