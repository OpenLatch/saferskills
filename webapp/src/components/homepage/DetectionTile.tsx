import type { DetectionTile as TileData } from '@/data/homepage-constants'

interface Props {
  tile: TileData
}

/**
 * Single density-card detector tile (244 × 116) inside the detection
 * marquee. Phase A2 vocabulary `.dt-tile`. CSS owned by
 * `page-home.css::.dt-tile`. Hover state shifts the rail accent and lifts
 * the card 1px.
 *
 * Rendered as React (not a thin Astro shell) so it composes cleanly inside
 * the React-driven detection marquee tracks. Each tile deep-links to
 * `/methodology#<rule_id>` when a `ruleId` is present.
 */
export default function DetectionTile({ tile }: Props) {
  const href = tile.ruleId ? `/methodology#${tile.ruleId}` : '#'
  return (
    <a className={`dt-tile sev-${tile.sev}`} href={href}>
      <div className="dt-top">
        <span className="dt-cat">{tile.cat}</span>
        <span
          className={`dt-sw sw-${tile.sev}`}
          title={`Severity ${tile.sev.toUpperCase()}`}
        ></span>
      </div>
      <div className="dt-name">{tile.title}</div>
      {tile.hint && (
        <div className="dt-hint">
          <span className="dt-hint-arrow">▸</span>
          {tile.hint}
        </div>
      )}
      <div className="dt-foot">
        <span className="dt-id">{tile.ruleId ?? '—'}</span>
      </div>
    </a>
  )
}
