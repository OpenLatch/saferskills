import RangeSlider from '../atoms/RangeSlider'
import RuntimeMonogram, { RUNTIME_IDS, runtimeLabel } from '../atoms/RuntimeMonogram'
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

// Mockup period presets — single-select; the empty value is "All time".
const PERIOD_OPTIONS: MultiSelectOption[] = [
  { value: '', label: 'All time' },
  { value: '24h', label: 'Last 24 hours' },
  { value: '7d', label: 'Last 7 days' },
  { value: '30d', label: 'Last 30 days' },
  { value: 'quarter', label: 'Last quarter' },
]

const SEVERITY_OPTIONS: MultiSelectOption[] = [
  { value: 'critical', label: 'Critical', icon: <span className="sq cr" aria-hidden="true" /> },
  { value: 'high', label: 'High', icon: <span className="sq hi" aria-hidden="true" /> },
  { value: 'info', label: 'Info', icon: <span className="sq in" aria-hidden="true" /> },
  {
    value: 'no-findings',
    label: 'No findings',
    icon: <span className="sq ok" aria-hidden="true" />,
  },
]

// Mockup panel order (≠ the canonical id order in RUNTIME_IDS).
const RUNTIME_ORDER = [
  'claude-code',
  'cursor',
  'windsurf',
  'copilot',
  'codex',
  'gemini',
  'cline',
  'openclaw',
] as const

const RUNTIME_OPTIONS: MultiSelectOption[] = RUNTIME_ORDER.filter((id) =>
  RUNTIME_IDS.includes(id)
).map((id) => ({
  value: id,
  label: runtimeLabel(id),
  icon: <RuntimeMonogram runtime={id} />,
}))

const SORT_OPTIONS: MultiSelectOption[] = [
  { value: 'newest', label: 'Newest' },
  { value: 'score_asc', label: 'Lowest score' },
  { value: 'score_desc', label: 'Highest score' },
]

/**
 * AgentFilterBar — the one-line `/agents` filter toolbar band (I-5.6 §12.2,
 * D-5.6-09): search · dual-handle score-range slider · Period preset ·
 * Agent (runtime) / Findings multiselects · sort. Markup mirrors the locked
 * mockup `.filterbar` band (a full-bleed paper-deep strip whose container is
 * the flex row). Presentational: the parent island owns URL-sync + the fetch.
 * CSS (`.filterbar` / `.fb-*` / `.ms-*`) is in `page-agent-directory.css`.
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
      <div className="container">
        <div className="fb-search">
          <svg viewBox="0 0 24 24" aria-hidden="true">
            <circle cx="11" cy="11" r="7" />
            <path d="m20 20-3.5-3.5" />
          </svg>
          <input
            type="search"
            value={value.q}
            placeholder="Search assessed agents…"
            aria-label="Search assessed agents"
            autoComplete="off"
            onChange={(e) => onChange({ q: e.currentTarget.value })}
          />
        </div>

        <div className="fb-rng">
          <span className="lbl">
            Score{' '}
            <b>
              {value.scoreMin}–{value.scoreMax}
            </b>
          </span>
          <RangeSlider
            min={value.scoreMin}
            max={value.scoreMax}
            onChange={(min, max) => onChange({ scoreMin: min, scoreMax: max })}
            minAriaLabel="Minimum score"
            maxAriaLabel="Maximum score"
            label="Score range"
            showCaption={false}
          />
        </div>

        <MultiSelect
          label="Period"
          allLabel="All time"
          variant="radio"
          ariaLabel="Filter by time period"
          options={PERIOD_OPTIONS}
          selected={value.period}
          onChange={(period) => onChange({ period })}
        />
        <MultiSelect
          label="Agent"
          allLabel="All"
          ariaLabel="Filter by agent runtime"
          options={RUNTIME_OPTIONS}
          selected={value.runtime}
          onChange={(runtime) => onChange({ runtime })}
        />
        <MultiSelect
          label="Findings"
          allLabel="Any"
          showBox={false}
          ariaLabel="Filter by findings severity"
          options={SEVERITY_OPTIONS}
          selected={value.severity}
          onChange={(severity) => onChange({ severity })}
        />
        <MultiSelect
          label="Sort"
          allLabel="Newest"
          variant="radio"
          ariaLabel="Sort agents"
          options={SORT_OPTIONS}
          selected={[value.sort]}
          onChange={([sort]) => onChange({ sort: (sort as AgentSortKey) ?? 'newest' })}
        />
      </div>
    </div>
  )
}
