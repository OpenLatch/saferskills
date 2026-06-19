import type { Story } from '@ladle/react'

/**
 * RecentScanCard — `.scan-card.recent` vocabulary.
 *
 * The Astro shell is mirrored as plain React here so Ladle can render the
 * static HTML structure for visual review. The CSS contract lives in
 * `webapp/src/styles/page-home.css::.feeds-band .scan-card.recent`.
 */
const TIER_TO_BAND = { g: 'Green', y: 'Yellow', o: 'Orange', r: 'Red' } as const
const TIER_TO_LETTER = { g: 'G', y: 'Y', o: 'O', r: 'O' } as const

const Mirror = ({
  name,
  author,
  score,
  tier,
  scannedAtRelative,
  findingCount,
}: {
  name: string
  author: string
  score: number
  tier: keyof typeof TIER_TO_BAND
  scannedAtRelative: string
  findingCount?: number
}) => {
  const iconMod = tier === 'g' ? '' : tier === 'y' ? 'yellow' : 'orange'
  const swClass = tier === 'g' ? 'green' : tier === 'y' ? 'yellow' : 'orange'
  return (
    <div className="feeds-band" style={{ maxWidth: 400 }}>
      <div className="mosaic" style={{ display: 'block' }}>
        <a className="scan-card recent" href="#" aria-label={`${name} — score ${score}`}>
          <div className="row">
            <div className="body">
              <div className="rank-pill">SCAN · {scannedAtRelative}</div>
              <div className="name">{name}</div>
              <div className="meta">
                {author} · skill
                {typeof findingCount === 'number' && findingCount > 0 && (
                  <span className="warn"> · {findingCount} finding{findingCount === 1 ? '' : 's'}</span>
                )}
              </div>
            </div>
            <span className={`icon-mark ${iconMod}`.trim()}>{TIER_TO_LETTER[tier]}</span>
          </div>
          <div className="score-line">
            <span className="score-num">{score}<span className="slash">/100</span></span>
            <span className="band"><span className={`sw ${swClass}`}></span>{TIER_TO_BAND[tier]}</span>
          </div>
        </a>
      </div>
    </div>
  )
}

export const Green: Story = () => (
  <Mirror name="github-mcp" author="acme" score={87} tier="g" scannedAtRelative="2m ago" />
)
export const Yellow: Story = () => (
  <Mirror name="obsidian-mcp" author="tana" score={71} tier="y" scannedAtRelative="8m ago" findingCount={1} />
)
export const Orange: Story = () => (
  <Mirror name="slack-bot" author="alice" score={42} tier="o" scannedAtRelative="5m ago" findingCount={2} />
)
