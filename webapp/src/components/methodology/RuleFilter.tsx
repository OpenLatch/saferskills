import { useEffect, useId, useState } from 'react'

interface Group {
  key: string
  title: string
  weight: number
  count: number
}

interface Props {
  /** Per-category counts from the generated sidecar (ruleStats). */
  groups: ReadonlyArray<Group>
  /** Total rule count (the "All" pill + denominator). */
  total: number
  /** id of the SSR'd container holding the .rule-group / .rule-card nodes. */
  targetId?: string
}

const SEVERITIES = [
  { key: 'critical', label: 'Critical' },
  { key: 'high', label: 'High' },
  { key: 'medium', label: 'Medium' },
  { key: 'low', label: 'Low' },
  { key: 'info', label: 'Info' },
] as const

/**
 * RuleFilter — sticky toolbar that narrows the (server-rendered) rule list by
 * category, severity, and free text. It is a progressive enhancement: the rules
 * are fully rendered in the DOM by Astro, and this island only toggles the
 * `hidden` attribute on `.rule-card` / `.rule-group` nodes in `targetId`. With
 * JS off, every rule is simply shown unfiltered.
 */
export default function RuleFilter({ groups, total, targetId = 'rules-index' }: Props) {
  const [cat, setCat] = useState<string>('all')
  const [sev, setSev] = useState<string>('all')
  const [q, setQ] = useState('')
  const [shown, setShown] = useState(total)
  const searchId = useId()

  useEffect(() => {
    const root = document.getElementById(targetId)
    if (!root) return
    const needle = q.trim().toLowerCase()
    let visible = 0
    for (const card of Array.from(root.querySelectorAll<HTMLElement>('.rule-card'))) {
      const okCat = cat === 'all' || card.dataset.category === cat
      const okSev = sev === 'all' || card.dataset.severity === sev
      const okQ = needle === '' || (card.dataset.search ?? '').includes(needle)
      const match = okCat && okSev && okQ
      card.toggleAttribute('hidden', !match)
      if (match) visible++
    }
    const filtering = cat !== 'all' || sev !== 'all' || needle !== ''
    for (const group of Array.from(root.querySelectorAll<HTMLElement>('.rule-group'))) {
      const anyVisible = group.querySelector('.rule-card:not([hidden])') !== null
      // Hide a whole category section once none of its cards survive the filter.
      group.toggleAttribute('hidden', !anyVisible)
      // When a filter is active, force matching groups open so results aren't
      // stranded behind a collapsed fold (the user's manual fold is restored
      // simply by clearing the filter).
      if (filtering && anyVisible && group.classList.contains('is-collapsed')) {
        group.classList.remove('is-collapsed')
        group.querySelector('.rg-head')?.setAttribute('aria-expanded', 'true')
      }
    }
    setShown(visible)
  }, [cat, sev, q, targetId])

  const isFiltered = cat !== 'all' || sev !== 'all' || q.trim() !== ''

  const reset = () => {
    setCat('all')
    setSev('all')
    setQ('')
  }

  return (
    <section className="rule-filter" aria-label="Filter detection rules">
      <div className="rf-row rf-row--top">
        <div className="rf-cats">
          <button
            type="button"
            className="rf-pill"
            aria-pressed={cat === 'all'}
            onClick={() => setCat('all')}
          >
            All <span className="rf-pill-n">{total}</span>
          </button>
          {groups.map((g) => (
            <button
              type="button"
              key={g.key}
              className="rf-pill"
              aria-pressed={cat === g.key}
              onClick={() => setCat(g.key)}
            >
              {g.title} <span className="rf-pill-n">{g.count}</span>
            </button>
          ))}
        </div>

        <div className="rf-search">
          <label className="rf-search-lbl" htmlFor={searchId}>
            Search rules
          </label>
          <input
            id={searchId}
            type="search"
            className="rf-search-input"
            placeholder="Filter by rule ID or trigger…"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            autoComplete="off"
            spellCheck={false}
          />
        </div>
      </div>

      <div className="rf-row rf-row--controls">
        <fieldset className="rf-sevs">
          <legend className="rf-sevs-legend">Severity</legend>
          <button
            type="button"
            className="rf-sev"
            aria-pressed={sev === 'all'}
            onClick={() => setSev('all')}
          >
            Any severity
          </button>
          {SEVERITIES.map((s) => (
            <button
              type="button"
              key={s.key}
              className={`rf-sev rf-sev--${s.key}`}
              aria-pressed={sev === s.key}
              onClick={() => setSev(sev === s.key ? 'all' : s.key)}
            >
              <span className="rf-sev-dot" aria-hidden="true" />
              {s.label}
            </button>
          ))}
        </fieldset>

        <div className="rf-status" aria-live="polite">
          Showing <b>{shown}</b> of {total} rules
          {isFiltered ? (
            <button type="button" className="rf-clear" onClick={reset}>
              Clear filters
            </button>
          ) : null}
        </div>
      </div>

      {shown === 0 ? (
        <p className="rf-empty">
          No rules match these filters. Try clearing the search or severity.
        </p>
      ) : null}
    </section>
  )
}
