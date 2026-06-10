export type ComponentKind = 'skill' | 'mcp_server' | 'hook' | 'plugin' | 'rules'
export type ComponentTier = 'green' | 'yellow' | 'orange' | 'red' | 'unscoped'

export interface ComponentScoreRowData {
  kind: ComponentKind
  name: string
  path?: string | null
  score: number
  tier: ComponentTier
  /** Catalog slug — the row deep-links to `/items/<slug>` (D-5.6-10). */
  slug: string
}

const TIER_CELL: Record<ComponentTier, string> = {
  green: 'g',
  yellow: 'y',
  orange: 'o',
  red: 'r',
  unscoped: '',
}

/** Glyph modifier (`.cs-mk`): MCP gets the circle, hook the diamond, the rest the square. */
const KIND_GLYPH: Record<ComponentKind, string> = {
  skill: 'skill',
  mcp_server: 'mcp',
  hook: 'hook',
  plugin: 'skill',
  rules: 'skill',
}

const KIND_LABEL: Record<ComponentKind, string> = {
  skill: 'Skill',
  mcp_server: 'MCP',
  hook: 'Hook',
  plugin: 'Plugin',
  rules: 'Rules',
}

export interface ComponentScoresTableProps {
  rows: ComponentScoreRowData[]
  /** Deep-link base; defaults to `/items` (the catalog item report, D-5.6-10). */
  basePath?: string
}

/**
 * Component Scores tab (I-5.6 §3.3, D-5.6-10) — the per-capability score grid.
 * **Contributing context only — never fused into the behavioral score.** Each
 * row deep-links to `/items/<slug>`; the all-clear / needs-review chip derives
 * from `tier` (the DTO has no `summary`/`needs_review`/`scan_id`). Renders a clean
 * empty-state when there are no assembled capabilities (the live builder is
 * data-starved until I-5.5 populates it). CSS `.cs-*` is DS-owned in components.css.
 */
export default function ComponentScoresTable({
  rows,
  basePath = '/items',
}: ComponentScoresTableProps) {
  if (rows.length === 0) {
    return (
      <p className="cs-empty">
        No assembled capabilities to show — this Agent Scan graded behavior only.
      </p>
    )
  }
  return (
    <div className="ar-components-tab">
      <p className="cs-note">
        <b>Contributing context only</b> — never fused into the behavioral score.
      </p>
      <div className="cs-grid cs-grid-boxed">
        {rows.map((r) => {
          const clear = r.tier === 'green'
          return (
            <a
              className={`cs-cell ${TIER_CELL[r.tier]}`.trim()}
              href={`${basePath}/${r.slug}`}
              key={r.slug}
              aria-label={`View report for ${r.name}`}
            >
              <span className={`cs-mk ${KIND_GLYPH[r.kind]}`} aria-hidden="true" />
              <span className="cs-id">
                <span className="nm">{r.name}</span>
                <span className="ty">
                  {KIND_LABEL[r.kind]}
                  {r.path ? ` · ${r.path}` : ''}
                </span>
              </span>
              <span className={`cs-chip ${clear ? 'clear' : 'review'}`}>
                {clear ? 'all-clear' : 'needs review'}
              </span>
              <span className="cs-num">{r.score}</span>
              <span className="cs-go" aria-hidden="true">
                →
              </span>
            </a>
          )
        })}
      </div>
    </div>
  )
}
