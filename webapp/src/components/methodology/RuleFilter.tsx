import { useEffect, useId, useMemo, useState } from 'react'
import type { RuleRow } from '@/generated/methodology/rules-table'
import { track } from '@/lib/analytics'
import { toCsv } from '@/lib/csv'
import { stripInlineCode } from '@/lib/rule-prose'

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
  /** Full per-rule data for the CSV export (joined to visible cards by ruleId). */
  rows: ReadonlyArray<RuleRow>
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

// Bucketed export count per telemetry.md (never a raw count).
function countBucket(n: number): '0' | '1' | '2-5' | '6-20' | '21+' {
  if (n <= 0) return '0'
  if (n === 1) return '1'
  if (n <= 5) return '2-5'
  if (n <= 20) return '6-20'
  return '21+'
}

const CSV_HEADER = [
  'Name',
  'Rule ID',
  'Severity',
  'Weight',
  'Status',
  'Sub-score',
  'Category',
  'Applies to',
  'Description',
  'Severity rationale',
  'Remediation',
  'Frameworks',
  'Detection logic',
  'Limitations',
  'Source',
] as const

function rowToCells(r: RuleRow): string[] {
  return [
    r.name,
    r.ruleId,
    r.severity,
    String(r.weight),
    r.status,
    r.category,
    r.categoryLabel,
    r.appliesTo.join('; '),
    stripInlineCode(r.description),
    r.severityRationale ? stripInlineCode(r.severityRationale) : '',
    stripInlineCode(r.remediationAction),
    r.frameworks.map((f) => `${f.id} ${f.label}`).join('; '),
    r.detection,
    r.limitations.join(' | '),
    r.sourceUrl,
  ]
}

/**
 * RuleFilter — sticky toolbar that narrows the (server-rendered) rule list by
 * category, severity, and free text, plus a CSV export of the currently-visible
 * rules. It is a progressive enhancement: the rules are fully rendered in the DOM
 * by Astro, and this island only toggles the `hidden` attribute on `.rule-card` /
 * `.rule-group` nodes in `targetId`. The richer search (name / description /
 * category / framework) needs no predicate change — the card's `data-search` is the
 * generator-supplied search index, so the DOM stays the single filter authority.
 */
export default function RuleFilter({ groups, total, rows, targetId = 'rules-index' }: Props) {
  const [cat, setCat] = useState<string>('all')
  const [sev, setSev] = useState<string>('all')
  const [q, setQ] = useState('')
  const [shown, setShown] = useState(total)
  // Reveal the Export button only after hydration so it is never an inert SSR
  // control (with JS off the methodology list still renders fully unfiltered).
  const [mounted, setMounted] = useState(false)
  const searchId = useId()

  // ruleId.toLowerCase() === the card's DOM id (anchorId) — the join key.
  const rowByKey = useMemo(() => {
    const m = new Map<string, RuleRow>()
    for (const r of rows) m.set(r.ruleId.toLowerCase(), r)
    return m
  }, [rows])

  useEffect(() => {
    setMounted(true)
  }, [])

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

  // Export reads the CURRENTLY-VISIBLE cards straight from the DOM (the one filter
  // authority) and joins them to `rows` — no second predicate to drift.
  const exportCsv = () => {
    const root = document.getElementById(targetId)
    if (!root) return
    const cards = Array.from(root.querySelectorAll<HTMLElement>('.rule-card:not([hidden])'))
    const picked: RuleRow[] = []
    for (const card of cards) {
      const row = rowByKey.get(card.id)
      if (row) picked.push(row)
    }
    if (picked.length === 0) return
    const csv = toCsv([CSV_HEADER as unknown as string[], ...picked.map(rowToCells)])
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `saferskills-rules-${picked.length}.csv`
    document.body.appendChild(a)
    a.click()
    a.remove()
    URL.revokeObjectURL(url)
    track('rule_csv_exported', { count_bucket: countBucket(picked.length) })
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
            placeholder="Filter by name, rule ID, framework, or trigger…"
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
          {mounted ? (
            <button
              type="button"
              className="rf-export"
              onClick={exportCsv}
              disabled={shown === 0}
              title="Download the visible rules as CSV"
            >
              ↓ Export CSV
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
