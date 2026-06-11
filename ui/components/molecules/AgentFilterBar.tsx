import Input from '../atoms/Input'
import RangeSlider from '../atoms/RangeSlider'
import RuntimeMonogram, { RUNTIME_IDS, runtimeLabel } from '../atoms/RuntimeMonogram'
import Select from '../atoms/Select'
import MultiSelect, { type MultiSelectOption } from './MultiSelect'

export type AgentSortKey = 'newest' | 'score_asc' | 'score_desc'

export interface AgentFilters {
  q: string
  scoreMin: number
  scoreMax: number
  period: string[]
  runtime: string[]
  severity: string[]
  sort: AgentSortKey
}

export const DEFAULT_AGENT_FILTERS: AgentFilters = {
  q: '',
  scoreMin: 0,
  scoreMax: 100,
  period: [],
  runtime: [],
  severity: [],
  sort: 'newest',
}

const PERIOD_OPTIONS: MultiSelectOption[] = [
  { value: '24h', label: 'Past 24h' },
  { value: '7d', label: 'Past 7 days' },
  { value: '30d', label: 'Past 30 days' },
  { value: 'quarter', label: 'Past quarter' },
]

const SEVERITY_OPTIONS: MultiSelectOption[] = [
  { value: 'critical', label: 'Critical' },
  { value: 'high', label: 'High' },
  { value: 'info', label: 'Info' },
  { value: 'no-findings', label: 'No findings' },
]

const RUNTIME_OPTIONS: MultiSelectOption[] = RUNTIME_IDS.map((id) => ({
  value: id,
  label: runtimeLabel(id),
  icon: <RuntimeMonogram runtime={id} />,
}))

const SORT_OPTIONS = [
  { value: 'newest', label: 'Newest' },
  { value: 'score_asc', label: 'Lowest score' },
  { value: 'score_desc', label: 'Highest score' },
]

/**
 * AgentFilterBar — the one-line `/agents` filter toolbar (I-5.6 §12.2, D-5.6-09):
 * search · dual-handle score-range slider · Period / Agent(runtime) / Findings
 * multiselects · sort. Presentational: the parent island owns URL-sync + the
 * fetch. CSS (`.filterbar` / `.fb-*`) is in `page-agent-directory.css`.
 */
export default function AgentFilterBar({
  value,
  onChange,
}: {
  value: AgentFilters
  /** Patch-merge update — the parent commits + URL-syncs + refetches. */
  onChange: (patch: Partial<AgentFilters>) => void
}) {
  return (
    <div className="filterbar" role="search">
      <div className="fb-search">
        <Input
          prefix="⌕"
          type="search"
          value={value.q}
          placeholder="Search assessed agents…"
          aria-label="Search assessed agents"
          onChange={(e) => onChange({ q: e.currentTarget.value })}
        />
      </div>

      <div className="fb-rng">
        <RangeSlider
          min={value.scoreMin}
          max={value.scoreMax}
          onChange={(min, max) => onChange({ scoreMin: min, scoreMax: max })}
          minAriaLabel="Minimum score"
          maxAriaLabel="Maximum score"
          minCapLabel="min"
          maxCapLabel="max"
          label="Score range"
        />
      </div>

      <MultiSelect
        label="Period"
        ariaLabel="Filter by time period"
        options={PERIOD_OPTIONS}
        selected={value.period}
        onChange={(period) => onChange({ period })}
      />
      <MultiSelect
        label="Agent"
        ariaLabel="Filter by agent runtime"
        options={RUNTIME_OPTIONS}
        selected={value.runtime}
        onChange={(runtime) => onChange({ runtime })}
      />
      <MultiSelect
        label="Findings"
        ariaLabel="Filter by findings severity"
        options={SEVERITY_OPTIONS}
        selected={value.severity}
        onChange={(severity) => onChange({ severity })}
      />

      <div className="fb-sort">
        <Select
          value={value.sort}
          options={SORT_OPTIONS}
          ariaLabel="Sort agents"
          onChange={(v) => onChange({ sort: v as AgentSortKey })}
        />
      </div>
    </div>
  )
}
