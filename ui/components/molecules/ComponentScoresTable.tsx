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

const TIER_BAND: Record<ComponentTier, string> = {
  green: 'g',
  yellow: 'y',
  orange: 'o',
  red: 'r',
  unscoped: '',
}

const KIND_GLYPH: Record<ComponentKind, string> = {
  skill: 'skill',
  mcp_server: 'mcp',
  hook: 'hook',
  plugin: 'plugin',
  rules: 'rules',
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
 * Component Scores tab (I-5.6 §3.3, D-5.6-10) — the per-capability score table,
 * reusing the scan report's `.cap-list`/`.cap-row` grammar exactly as the locked
 * mockup does. **Contributing context only — never fused into the behavioral
 * score.** Each row deep-links to `/items/<slug>`; the all-clear / needs-review
 * chip derives from `tier` (the DTO has no `summary` field). Renders a clean
 * empty-state when there are no assembled capabilities (the live builder is
 * data-starved until I-5.5 populates it). The `.cap-*` CSS ships with
 * `page-scan-report.css`, which every agent-report route imports.
 */
export default function ComponentScoresTable({
  rows,
  basePath = '/items',
}: ComponentScoresTableProps) {
  if (rows.length === 0) {
    return (
      <section className="ar-empty ar-empty--na" aria-label="No component scores in this scan">
        <p className="cv-eyebrow">
          Component scores · <b>Not in this scan</b>
        </p>
        <h3 className="cv-title">Behavior graded as one system.</h3>
        <p className="cv-lede">
          This Agent Scan probed the assembled agent — model, harness, identity and permissions
          — as a single system. Per-capability scores appear when a scan bundles named skills,
          MCP servers, hooks or plugins.
        </p>
        <ul className="csx-kinds" aria-hidden="true">
          <li className="csx-chip">Skill</li>
          <li className="csx-chip">MCP</li>
          <li className="csx-chip">Hook</li>
          <li className="csx-chip">Plugin</li>
          <li className="csx-chip">Rules</li>
        </ul>
        <a className="csx-link" href="/methodology">
          How component scores work →
        </a>
      </section>
    )
  }
  return (
    <div className="ar-components-tab">
      <p className="ar-panel-lead">
        Each capability's own score, shown as <b>contributing context</b> only — they are never
        fused into the behavioral score. Open any to read its full report.
      </p>
      <div className="cap-list">
        <div className="cap-row cap-headrow">
          <span>Type</span>
          <span>Capability</span>
          <span>Security summary</span>
          <span>Score</span>
          <span>Report</span>
        </div>
        {rows.map((r) => {
          const clear = r.tier === 'green'
          return (
            <div className={`cap-row ${TIER_BAND[r.tier]}`.trim()} key={r.slug}>
              <span className={`cap-type ${KIND_GLYPH[r.kind]}`}>
                <span className="g-mk" aria-hidden="true" />
                {KIND_LABEL[r.kind]}
              </span>
              <div className="cap-id">
                <span className="nm">{r.name}</span>
                {r.path && <span className="pth">{r.path}</span>}
              </div>
              <div className="cap-note">
                Scored on its own {KIND_LABEL[r.kind]} rubric.
                <span className={`find ${clear ? 'clear' : 'warn'}`}>
                  {clear ? 'all clear' : 'needs review'}
                </span>
              </div>
              <div className="cap-score">
                <span className="num">
                  {r.score}
                  <i>/100</i>
                </span>
              </div>
              <div className="cap-action">
                <a className="open" href={`${basePath}/${r.slug}`}>
                  View report →
                </a>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
